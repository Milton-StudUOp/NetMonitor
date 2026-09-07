import asyncio
from time import perf_counter

import pytest

from app.api import discovery
from app.schemas.platform import DiscoveryRequest


async def run_scan(monkeypatch, mode="NONE", ports=None):
    checked_ports = []

    async def fake_ping(ip, **_kwargs):
        return {"is_up": ip.endswith(".1"), "latency_ms": 2.5 if ip.endswith(".1") else None}

    async def fake_open(ip, port, _options, _limiter):
        checked_ports.append((ip, port))
        return port in {22, 443}

    async def no_snmp(*_args): return {}
    async def no_hostname(_ip): return "gateway.example" 

    monkeypatch.setattr(discovery, "ping_target", fake_ping)
    monkeypatch.setattr(discovery, "_open_port", fake_open)
    monkeypatch.setattr(discovery, "_snmp_identity", no_snmp)
    monkeypatch.setattr(discovery, "_hostname", no_hostname)
    monkeypatch.setattr(discovery, "_arp_seen", lambda _ip: False)
    request = DiscoveryRequest(target="192.0.2.1-192.0.2.2", port_scan_mode=mode, ports=ports or [])
    job = {"request": request, "targets": discovery._parse_target(request.target), "status": "RUNNING", "stage": "HOST_DISCOVERY", "total_hosts": 2, "hosts_processed": 0, "hosts_found": 0, "ports_scanned": 0, "total_port_checks": 0, "results": [], "error": None, "started_at": perf_counter()}
    await discovery._run_scan(job)
    return job, checked_ports


@pytest.mark.asyncio
async def test_basic_discovery_runs_without_port_scan(monkeypatch):
    job, checked = await run_scan(monkeypatch)
    assert checked == []
    assert [item["ip_address"] for item in job["results"]] == ["192.0.2.1"]
    assert job["results"][0]["open_ports"] == []


@pytest.mark.asyncio
async def test_top_100_scans_only_active_hosts(monkeypatch):
    job, checked = await run_scan(monkeypatch, "TOP_100")
    assert len(discovery.TOP_100_TCP_PORTS) == 100
    assert len(checked) == 100
    assert {ip for ip, _ in checked} == {"192.0.2.1"}
    assert job["results"][0]["open_ports"] == [22, 443]


@pytest.mark.asyncio
async def test_custom_mode_scans_only_requested_ports(monkeypatch):
    _job, checked = await run_scan(monkeypatch, "CUSTOM", [22, 80, 443, 3389])
    assert [port for _, port in checked] == [22, 80, 443, 3389]


@pytest.mark.asyncio
async def test_empty_custom_ports_remains_valid_discovery(monkeypatch):
    request = DiscoveryRequest(target="192.0.2.1", port_scan_mode="CUSTOM", ports=[])
    assert request.ports == []
    job, checked = await run_scan(monkeypatch, "CUSTOM", [])
    assert checked == []
    assert job["hosts_found"] == 1


@pytest.mark.parametrize(("identity", "expected"), [
    ({"model": "Cisco IOS Software, Catalyst 9300"}, "SWITCH"),
    ({"model": "MikroTik RouterOS 7.20"}, "ROUTER"),
    ({"model": "FortiGate-VM64 FortiOS"}, "FIREWALL"),
    ({"hostname": "unifi-ap-office", "manufacturer": "Ubiquiti"}, "ACCESS_POINT"),
    ({"model": "Linux server 6.8.0"}, "SERVER"),
])
def test_device_type_is_inferred_from_discovered_identity(identity, expected):
    assert discovery._guess_type([], **identity) == expected


def test_device_type_uses_snmp_services_when_description_is_generic():
    assert discovery._guess_type([], sys_services=4) == "ROUTER"
    assert discovery._guess_type([], sys_services=72) == "SERVER"
