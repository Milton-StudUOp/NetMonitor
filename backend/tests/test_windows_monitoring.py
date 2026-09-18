import pytest

from app.services.windows_monitoring import WindowsMonitoringError, WindowsMonitoringProvider


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
