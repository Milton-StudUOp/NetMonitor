from datetime import datetime, timedelta, timezone

import pytest
from app.models.device import Device, DeviceType
from app.models.monitoring_provider import DeviceCapability
from app.services.monitoring_engine import MonitoringEngine
from app.services.windows_monitoring_engine import WindowsMonitoringEngine
import app.services.monitoring_engine as monitoring_module


def test_device_probe_schedule_uses_persisted_last_probe_time():
    engine = MonitoringEngine()
    now = datetime.now(timezone.utc)
    device = Device(name="edge-1", ip_address="192.0.2.10", device_type=DeviceType.ROUTER,
                    location="test", monitoring_interval=30)

    assert engine._device_is_due(device, now) is True
    device.last_monitored_at = now - timedelta(seconds=29)
    assert engine._device_is_due(device, now) is False
    device.last_monitored_at = now - timedelta(seconds=30)
    assert engine._device_is_due(device, now) is True


def test_naive_last_probe_time_is_normalized_for_mysql_compatibility():
    engine = MonitoringEngine()
    now = datetime.now(timezone.utc)
    device = Device(name="edge-2", ip_address="192.0.2.11", device_type=DeviceType.ROUTER,
                    location="test", monitoring_interval=60,
                    last_monitored_at=(now - timedelta(seconds=10)).replace(tzinfo=None))

    assert engine._device_is_due(device, now) is False


def test_metric_schedule_is_durable_and_accepts_naive_database_timestamps():
    due_before = datetime.now(timezone.utc) - timedelta(seconds=60)
    capability = DeviceCapability(device_id=1, provider="SNMP")
    assert WindowsMonitoringEngine._metric_is_due(capability, due_before) is True
    capability.last_metric_collected_at = (due_before + timedelta(seconds=1)).replace(tzinfo=None)
    assert WindowsMonitoringEngine._metric_is_due(capability, due_before) is False


@pytest.mark.asyncio
async def test_one_thousand_device_probes_respect_the_configured_concurrency(monkeypatch):
    engine = MonitoringEngine()
    engine._probe_concurrency = 23
    active = 0
    peak = 0

    async def probe(_ip, count=2):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            import asyncio
            await asyncio.sleep(0)
            return {"is_up": True, "latency_ms": 1.0, "packet_loss_pct": 0.0}
        finally:
            active -= 1

    monkeypatch.setattr(monitoring_module, "ping_target", probe)
    devices = [Device(name=f"edge-{number}", ip_address=f"192.0.2.{number % 255}",
                      device_type=DeviceType.ROUTER, location="test") for number in range(1000)]
    results = await engine._run_device_probes(devices)

    assert len(results) == 1000
    assert peak == 23
