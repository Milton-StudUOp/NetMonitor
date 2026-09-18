import pytest
from app.api import devices as devices_api
from app.api.devices import _reject_loopback_windows_target
from app.models.device import Device, DeviceType
from app.services.windows_monitoring import WindowsMonitoringError, WindowsMonitoringProvider
from app.services.windows_monitoring_engine import service_state_transition


class FakeTransport:
    endpoint = "https://server:5986/wsman"

    def __init__(self, response): self.response = response

    async def run_powershell(self, script):
        if isinstance(self.response, Exception): raise self.response
        return self.response


@pytest.mark.asyncio
async def test_modern_windows_selects_cim_provider():
    provider = WindowsMonitoringProvider(FakeTransport(
        '{"operating_system":"Microsoft Windows Server 2019","powershell_version":"5.1.1"}'))
    result = await provider.detect_capabilities()
    assert result.provider_mode == "MODERN_CIM"
    assert result.capabilities["services"] is True
    assert result.diagnostics == {"transport": "winrm_https"}


@pytest.mark.asyncio
async def test_server_2008_compatible_powershell_selects_legacy_wmi():
    provider = WindowsMonitoringProvider(FakeTransport(
        '{"operating_system":"Microsoft Windows Server 2008 R2","powershell_version":"2.0"}'))
    result = await provider.detect_capabilities()
    assert result.provider_mode == "LEGACY_WMI"


@pytest.mark.asyncio
async def test_invalid_remote_response_is_safely_classified():
    provider = WindowsMonitoringProvider(FakeTransport("not-json"))
    with pytest.raises(WindowsMonitoringError) as error:
        await provider.detect_capabilities()
    assert error.value.code == "DISCOVERY_FAILED"
    assert "not-json" not in str(error.value)


@pytest.mark.asyncio
async def test_service_discovery_normalizes_legacy_wmi_output():
    provider = WindowsMonitoringProvider(FakeTransport(
        '[{"Name":"MSSQLSERVER","DisplayName":"SQL Server","State":"Running","StartMode":"Auto","StartName":"svc_sql"}]'))
    services = await provider.discover_services()
    assert services == [{"name": "MSSQLSERVER", "display_name": "SQL Server", "state": "running",
        "start_mode": "auto", "description": None, "service_account": "svc_sql", "monitoring_provider": "windows"}]


@pytest.mark.asyncio
async def test_batch_service_check_returns_normalized_states():
    provider = WindowsMonitoringProvider(FakeTransport(
        '[{"Name":"MSSQLSERVER","State":"Running"},{"Name":"Spooler","State":"Stopped"}]'))
    states = await provider.check_services(["MSSQLSERVER", "Spooler"])
    assert states == {"MSSQLSERVER": "running", "Spooler": "stopped"}


@pytest.mark.asyncio
async def test_system_metrics_are_normalized():
    provider = WindowsMonitoringProvider(FakeTransport(
        '{"cpu_percent":12,"memory_percent":63.5,"uptime_seconds":900,"storage":[]}'))
    metrics = await provider.collect_system_metrics()
    assert metrics["cpu_percent"] == 12
    assert metrics["uptime_seconds"] == 900


def test_service_state_requires_thresholds_and_recovers_gradually():
    state, failures, successes = service_state_transition("UP", False, 0, 2, 3, 2)
    assert (state, failures, successes) == ("SUSPECTED", 1, 0)
    state, failures, successes = service_state_transition(state, False, failures, successes, 3, 2)
    state, failures, successes = service_state_transition(state, False, failures, successes, 3, 2)
    assert state == "DOWN"
    state, failures, successes = service_state_transition(state, True, failures, successes, 3, 2)
    assert state == "RECOVERING"
    state, failures, successes = service_state_transition(state, True, failures, successes, 3, 2)
    assert state == "UP"


@pytest.mark.asyncio
async def test_service_check_batches_one_hundred_names_in_one_request():
    class CountingTransport(FakeTransport):
        def __init__(self): super().__init__('[]'); self.calls = 0
        async def run_powershell(self, script): self.calls += 1; return self.response
    transport = CountingTransport(); provider = WindowsMonitoringProvider(transport)
    await provider.check_services([f"Service{i}" for i in range(100)])
    assert transport.calls == 1


def test_loopback_is_allowed_when_backend_runs_on_windows(monkeypatch):
    monkeypatch.setattr(devices_api.os, "name", "nt")
    device = Device(name="local", ip_address="127.0.0.1", device_type=DeviceType.SERVER, location="lab")
    _reject_loopback_windows_target(device)
