import pytest

from app.services.snmp_monitoring import (
    OID_HR_STORAGE_ALLOCATION_UNITS,
    OID_HR_STORAGE_DESCR,
    OID_HR_STORAGE_SIZE,
    OID_HR_STORAGE_USED,
    OID_IF_ADMIN_STATUS,
    OID_IF_DESCR,
    OID_IF_IN_ERRORS,
    OID_IF_IN_OCTETS,
    OID_IF_MTU,
    OID_IF_OPER_STATUS,
    OID_IF_OUT_ERRORS,
    OID_IF_OUT_OCTETS,
    OID_IF_SPEED,
    OID_IF_TYPE,
    OID_SYS_DESCR,
    OID_SYS_UPTIME,
    SNMPMonitoringProvider,
)


class FakeSNMPTransport:
    async def get(self, *oids):
        values = {
            OID_SYS_DESCR: "Linux test appliance",
            OID_SYS_UPTIME: "12300",
        }
        return {oid: values[oid] for oid in oids}

    async def walk(self, oid, limit=500):
        tables = {
            OID_IF_DESCR: {1: "eth0"},
            OID_IF_TYPE: {1: "6"},
            OID_IF_MTU: {1: "1500"},
            OID_IF_SPEED: {1: "1000000000"},
            OID_IF_ADMIN_STATUS: {1: "1"},
            OID_IF_OPER_STATUS: {1: "1"},
            OID_IF_IN_OCTETS: {1: "1000"},
            OID_IF_OUT_OCTETS: {1: "2000"},
            OID_IF_IN_ERRORS: {1: "0"},
            OID_IF_OUT_ERRORS: {1: "1"},
            OID_HR_STORAGE_DESCR: {1: "/"},
            OID_HR_STORAGE_ALLOCATION_UNITS: {1: "1024"},
            OID_HR_STORAGE_SIZE: {1: "100"},
            OID_HR_STORAGE_USED: {1: "25"},
        }
        return tables.get(oid, {})


@pytest.mark.asyncio
async def test_snmp_capabilities_report_only_supported_metrics():
    provider = SNMPMonitoringProvider(FakeSNMPTransport())

    result = await provider.discover_metric_capabilities()

    assert result["uptime"]["supported"] is True
    assert result["network_interfaces"]["supported"] is True
    assert result["storage"]["supported"] is True
    assert result["cpu"]["supported"] is False
    assert result["memory"]["supported"] is False


@pytest.mark.asyncio
async def test_snmp_collects_network_storage_and_uptime():
    provider = SNMPMonitoringProvider(FakeSNMPTransport())

    result = await provider.collect_system_metrics()

    assert result["uptime_seconds"] == 123
    assert result["cpu_percent"] is None
    assert result["network_interfaces"][0]["name"] == "eth0"
    assert result["network_interfaces"][0]["oper_status"] == "up"
    assert result["storage"][0]["used_percent"] == 25


@pytest.mark.asyncio
async def test_snmp_keeps_available_metrics_when_optional_oids_are_missing():
    class PartialTransport(FakeSNMPTransport):
        async def walk(self, oid, limit=500):
            if oid in {OID_HR_STORAGE_DESCR, OID_HR_STORAGE_ALLOCATION_UNITS, OID_HR_STORAGE_SIZE, OID_HR_STORAGE_USED}:
                from app.services.snmp_monitoring import SNMPMonitoringError
                raise SNMPMonitoringError("SNMP_WALK_FAILED", "No such object")
            return await super().walk(oid, limit)

    provider = SNMPMonitoringProvider(PartialTransport())

    result = await provider.collect_system_metrics()

    assert result["uptime_seconds"] == 123
    assert result["network_interfaces"][0]["name"] == "eth0"
    assert result["storage"] == []


@pytest.mark.asyncio
async def test_snmp_interface_picker_uses_compact_inventory_walks_only():
    class CountingTransport(FakeSNMPTransport):
        def __init__(self): self.walked = []
        async def walk(self, oid, limit=500):
            self.walked.append(oid)
            return await super().walk(oid, limit)

    transport = CountingTransport()
    provider = SNMPMonitoringProvider(transport)
    interfaces = await provider.discover_interfaces()

    assert interfaces == [{"index": 1, "name": "eth0", "type": "ethernet",
                           "speed_bps": 1_000_000_000, "oper_status": "up"}]
    assert transport.walked == [OID_IF_DESCR, OID_IF_TYPE, OID_IF_SPEED, OID_IF_OPER_STATUS]
