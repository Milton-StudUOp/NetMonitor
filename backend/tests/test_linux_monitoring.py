import pytest

from app.services.linux_monitoring import LinuxMonitoringProvider


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.observed_host_key = "ssh-ed25519 AAAATEST"
        self.commands = []

    async def run(self, command):
        self.commands.append(command)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_linux_capabilities_report_only_available_features():
    provider = LinuxMonitoringProvider(FakeTransport(["""OS_BEGIN
PRETTY_NAME="Ubuntu 24.04 LTS"
ID=ubuntu
VERSION_ID="24.04"
OS_END
Linux 6.8 x86_64 GNU/Linux
/usr/bin/systemctl
PROC_OK
SYS_NET_OK
/usr/bin/df
/usr/sbin/ip"""]))
    result = await provider.detect_capabilities()
    assert result.operating_system == "Ubuntu 24.04 LTS"
    assert result.provider_mode == "SYSTEMD"
    assert result.capabilities["services"] is True
    assert result.capabilities["events"] is False
    assert result.diagnostics["host_key"] == "ssh-ed25519 AAAATEST"


@pytest.mark.asyncio
async def test_systemd_service_inventory_is_normalized():
    transport = FakeTransport(["""Id=nginx.service
Description=A high performance web server
ActiveState=active
SubState=running
UnitFileState=enabled

Id=backup.service
Description=Nightly backup
ActiveState=failed
SubState=failed
UnitFileState=disabled"""])
    provider = LinuxMonitoringProvider(transport)
    services = await provider.discover_services()
    assert services[0]["state"] == "running"
    assert services[0]["start_mode"] == "enabled"
    assert services[0]["monitoring_provider"] == "linux"
    assert services[1]["state"] == "stopped"
    assert "list-units --type=service --all" in transport.commands[0]
    assert "systemctl show" in transport.commands[0]


@pytest.mark.asyncio
async def test_linux_metrics_are_converted_to_shared_schema():
    response = """CPU1 cpu 100 0 100 800 0 0 0 0
CPU2 cpu 150 0 150 900 0 0 0 0
MEM_BEGIN
MemTotal: 1000 kB
MemAvailable: 250 kB
MEM_END
UPTIME 3661.10
DF_BEGIN
Filesystem 1-blocks Used Available Capacity Mounted on
/dev/sda1 100000 40000 60000 40% /
DF_END
NET_BEGIN
eth0|up|00:11:22:33:44:55|1000|2000
NET_END
SYS_BEGIN
linux-host
Linux 6.8 x86_64 GNU/Linux
PRETTY_NAME="Ubuntu 24.04 LTS"
VERSION_ID="24.04"
SYS_END
PROC_BEGIN
10 5.5 1024 nginx
PROC_END"""
    provider = LinuxMonitoringProvider(FakeTransport([response]))
    values = await provider.collect_system_metrics()
    assert values["cpu_percent"] == 50.0
    assert values["memory_percent"] == 75.0
    assert values["uptime_seconds"] == 3661
    assert values["storage"][0]["label"] == "/"
    assert values["network_interfaces"][0]["bytes_received"] == 1000
    assert values["processes"][0]["working_set_bytes"] == 1048576
