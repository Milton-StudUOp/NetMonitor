from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.monitoring_providers import CapabilityResult, MonitoringProvider, MonitoringProviderError


OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_IF_TYPE = "1.3.6.1.2.1.2.2.1.3"
OID_IF_MTU = "1.3.6.1.2.1.2.2.1.4"
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"
OID_HR_STORAGE_DESCR = "1.3.6.1.2.1.25.2.3.1.3"
OID_HR_STORAGE_ALLOCATION_UNITS = "1.3.6.1.2.1.25.2.3.1.4"
OID_HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
OID_HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"

STATUS_LABELS = {1: "up", 2: "down", 3: "testing"}
IF_TYPE_LABELS = {
    6: "ethernet",
    24: "loopback",
    53: "propVirtual",
    131: "tunnel",
    135: "l2vlan",
}


class SNMPMonitoringError(MonitoringProviderError):
    pass


@dataclass
class SNMPSecurity:
    version: str = "2c"
    community: str | None = None
    username: str | None = None
    auth_key: str | None = None
    priv_key: str | None = None
    auth_protocol: str = "SHA"
    priv_protocol: str = "AES"


@dataclass
class SNMPTransport:
    host: str
    security: SNMPSecurity
    port: int = 161
    timeout: float = 2.0
    retries: int = 1
    _engine: Any = field(default=None, init=False, repr=False)

    async def get(self, *oids: str) -> dict[str, Any]:
        try:
            from pysnmp.hlapi.asyncio import ContextData, ObjectIdentity, ObjectType, SnmpEngine, get_cmd
        except Exception as exc:
            raise SNMPMonitoringError("SNMP_LIBRARY_UNAVAILABLE", "PySNMP is not available") from exc
        engine = self._snmp_engine(SnmpEngine)
        target = await self._target()
        error_indication, error_status, error_index, var_binds = await get_cmd(
            engine, self._auth(), target, ContextData(), *(ObjectType(ObjectIdentity(oid)) for oid in oids)
        )
        if error_indication or error_status:
            raise SNMPMonitoringError("SNMP_QUERY_FAILED", str(error_indication or error_status))
        return {str(name): value.prettyPrint() for name, value in var_binds}

    async def walk(self, oid: str, limit: int = 500) -> dict[int, Any]:
        try:
            from pysnmp.hlapi.asyncio import ContextData, ObjectIdentity, ObjectType, SnmpEngine, walk_cmd
        except Exception as exc:
            raise SNMPMonitoringError("SNMP_LIBRARY_UNAVAILABLE", "PySNMP is not available") from exc
        engine = self._snmp_engine(SnmpEngine)
        target = await self._target()
        rows: dict[int, Any] = {}
        count = 0
        async for error_indication, error_status, error_index, var_binds in walk_cmd(
            engine, self._auth(), target, ContextData(), ObjectType(ObjectIdentity(oid)), lexicographicMode=False
        ):
            if error_indication or error_status:
                raise SNMPMonitoringError("SNMP_WALK_FAILED", str(error_indication or error_status))
            for name, value in var_binds:
                suffix = str(name)
                if not suffix.startswith(f"{oid}."):
                    continue
                try:
                    rows[int(suffix.rsplit(".", 1)[-1])] = value.prettyPrint()
                except ValueError:
                    continue
                count += 1
                if count >= limit:
                    return rows
        return rows

    def _snmp_engine(self, factory):
        if self._engine is None:
            self._engine = factory()
        return self._engine

    async def _target(self):
        from pysnmp.hlapi.asyncio import UdpTransportTarget
        return await UdpTransportTarget.create((self.host, self.port), timeout=self.timeout, retries=self.retries)

    def _auth(self):
        from pysnmp.hlapi.asyncio import (
            CommunityData,
            UsmUserData,
            usmAesCfb128Protocol,
            usmDESPrivProtocol,
            usmHMACMD5AuthProtocol,
            usmHMACSHAAuthProtocol,
            usmNoAuthProtocol,
            usmNoPrivProtocol,
        )
        if self.security.version.lower() in {"1", "v1"}:
            return CommunityData(self.security.community or "public", mpModel=0)
        if self.security.version.lower() in {"3", "v3"}:
            auth_protocol = {"MD5": usmHMACMD5AuthProtocol, "SHA": usmHMACSHAAuthProtocol}.get(
                self.security.auth_protocol.upper(), usmNoAuthProtocol
            )
            priv_protocol = {"DES": usmDESPrivProtocol, "AES": usmAesCfb128Protocol}.get(
                self.security.priv_protocol.upper(), usmNoPrivProtocol
            )
            return UsmUserData(
                self.security.username,
                self.security.auth_key,
                self.security.priv_key,
                authProtocol=auth_protocol,
                privProtocol=priv_protocol,
            )
        return CommunityData(self.security.community or "public", mpModel=1)


class SNMPMonitoringProvider(MonitoringProvider):
    def __init__(self, transport: SNMPTransport):
        self.transport = transport

    async def detect_capabilities(self) -> CapabilityResult:
        try:
            data = await self.transport.get(OID_SYS_DESCR, OID_SYS_UPTIME)
        except MonitoringProviderError:
            raise
        except Exception as exc:
            raise SNMPMonitoringError("SNMP_UNAVAILABLE", "SNMP agent is unavailable or not responding") from exc
        interfaces = await self._interfaces(limit=20)
        storage = await self._storage()
        sys_descr = data.get(OID_SYS_DESCR, "")
        uptime = _int_or_none(data.get(OID_SYS_UPTIME))
        capabilities = {
            "services": False,
            "processes": False,
            "events": False,
            "cpu": False,
            "memory": False,
            "uptime": uptime is not None,
            "storage": bool(storage),
            "network_interfaces": bool(interfaces),
            "system_information": True,
        }
        return CapabilityResult(
            operating_system=sys_descr or "SNMP managed device",
            powershell_version=None,
            provider_mode="SNMP",
            capabilities=capabilities,
            diagnostics={"interface_count": len(interfaces), "sys_descr": sys_descr},
        )

    async def discover_services(self) -> list[dict]:
        return []

    async def check_services(self, names: list[str]) -> dict[str, str]:
        return {name: "unknown" for name in names}

    async def collect_system_metrics(self) -> dict:
        values = await self.transport.get(OID_SYS_DESCR, OID_SYS_UPTIME)
        interfaces = await self._interfaces()
        storage = await self._storage()
        return {
            "cpu_percent": None,
            "memory_percent": None,
            "uptime_seconds": _ticks_to_seconds(_int_or_none(values.get(OID_SYS_UPTIME))),
            "storage": storage,
            "network_interfaces": interfaces,
            "network_adapters": interfaces,
            "processes": [],
            "events": [],
            "system_information": {"description": values.get(OID_SYS_DESCR), "provider": "SNMP"},
        }

    async def discover_metric_capabilities(self) -> dict[str, dict]:
        # Metric selection must respond before the full polling payload is
        # required. The former implementation called ``detect_capabilities``
        # here, then the UI called ``collect_system_metrics`` again to show
        # interfaces: two complete IF-MIB/HOST-RESOURCES-MIB walks before the
        # user could select anything. A lightweight capability check is enough
        # at this stage; the full walks remain part of actual collection.
        try:
            system = await self.transport.get(OID_SYS_UPTIME)
        except MonitoringProviderError:
            raise
        except Exception as exc:
            raise SNMPMonitoringError("SNMP_UNAVAILABLE", "SNMP agent is unavailable or not responding") from exc
        interfaces = await self._optional_walk(OID_IF_DESCR, limit=500)
        storage = await self._optional_walk(OID_HR_STORAGE_DESCR, limit=100)
        capabilities = {
            "cpu": False,
            "memory": False,
            "uptime": _int_or_none(system.get(OID_SYS_UPTIME)) is not None,
            "storage": bool(storage),
            "network_interfaces": bool(interfaces),
            "system_information": True,
        }
        labels = {
            "cpu": "CPU",
            "memory": "Memory",
            "uptime": "Uptime",
            "storage": "Storage",
            "network_interfaces": "Network interfaces",
            "system_information": "System information",
        }
        return {
            key: {
                "label": labels[key],
                "supported": bool(capabilities.get(key)),
                "source": "SNMP",
            }
            for key in labels
        }

    async def discover_interfaces(self, limit: int = 500) -> list[dict]:
        """Return the compact inventory used by the interface picker.

        Counters, errors, MTU, and storage are unnecessary before the user has
        selected interfaces. Omitting them removes slow walks from this UI path
        while regular monitoring still collects the full data set afterwards.
        """
        descriptions = await self._optional_walk(OID_IF_DESCR, limit=limit)
        if not descriptions:
            return []
        types = await self._optional_walk(OID_IF_TYPE, limit=limit)
        speeds = await self._optional_walk(OID_IF_SPEED, limit=limit)
        operational = await self._optional_walk(OID_IF_OPER_STATUS, limit=limit)
        return [{
            "index": index,
            "name": name,
            "type": IF_TYPE_LABELS.get(_int_or_none(types.get(index)), str(_int_or_none(types.get(index))) if _int_or_none(types.get(index)) is not None else None),
            "speed_bps": _int_or_none(speeds.get(index)),
            "oper_status": STATUS_LABELS.get(_int_or_none(operational.get(index)), "unknown"),
        } for index, name in sorted(descriptions.items())]

    async def _optional_walk(self, oid: str, limit: int = 500) -> dict[int, Any]:
        try:
            return await self.transport.walk(oid, limit=limit)
        except SNMPMonitoringError:
            # Network gear often implements only part of IF-MIB or
            # HOST-RESOURCES-MIB. Missing optional OIDs must not discard all
            # otherwise valid telemetry.
            return {}

    async def _interfaces(self, limit: int = 500) -> list[dict]:
        descriptions = await self._optional_walk(OID_IF_DESCR, limit=limit)
        if not descriptions:
            return []
        tables = {
            "type": await self._optional_walk(OID_IF_TYPE, limit=limit),
            "mtu": await self._optional_walk(OID_IF_MTU, limit=limit),
            "speed": await self._optional_walk(OID_IF_SPEED, limit=limit),
            "admin": await self._optional_walk(OID_IF_ADMIN_STATUS, limit=limit),
            "oper": await self._optional_walk(OID_IF_OPER_STATUS, limit=limit),
            "in_octets": await self._optional_walk(OID_IF_IN_OCTETS, limit=limit),
            "out_octets": await self._optional_walk(OID_IF_OUT_OCTETS, limit=limit),
            "in_errors": await self._optional_walk(OID_IF_IN_ERRORS, limit=limit),
            "out_errors": await self._optional_walk(OID_IF_OUT_ERRORS, limit=limit),
        }
        rows = []
        for index, name in sorted(descriptions.items()):
            if_type = _int_or_none(tables["type"].get(index))
            rows.append({
                "index": index,
                "name": name,
                "type": IF_TYPE_LABELS.get(if_type, str(if_type) if if_type is not None else None),
                "mtu": _int_or_none(tables["mtu"].get(index)),
                "speed_bps": _int_or_none(tables["speed"].get(index)),
                "admin_status": STATUS_LABELS.get(_int_or_none(tables["admin"].get(index)), "unknown"),
                "oper_status": STATUS_LABELS.get(_int_or_none(tables["oper"].get(index)), "unknown"),
                "bytes_received": _int_or_none(tables["in_octets"].get(index)),
                "bytes_sent": _int_or_none(tables["out_octets"].get(index)),
                "errors_received": _int_or_none(tables["in_errors"].get(index)),
                "errors_sent": _int_or_none(tables["out_errors"].get(index)),
            })
        return rows

    async def _storage(self) -> list[dict]:
        descriptions = await self._optional_walk(OID_HR_STORAGE_DESCR)
        if not descriptions:
            return []
        allocation_units = await self._optional_walk(OID_HR_STORAGE_ALLOCATION_UNITS)
        sizes = await self._optional_walk(OID_HR_STORAGE_SIZE)
        used = await self._optional_walk(OID_HR_STORAGE_USED)
        rows = []
        for index, name in sorted(descriptions.items()):
            unit = _int_or_none(allocation_units.get(index)) or 0
            size = (_int_or_none(sizes.get(index)) or 0) * unit
            used_bytes = (_int_or_none(used.get(index)) or 0) * unit
            rows.append({
                "name": name,
                "label": name,
                "size_bytes": size,
                "used_bytes": used_bytes,
                "free_bytes": max(0, size - used_bytes),
                "used_percent": round(used_bytes * 100 / size, 2) if size else None,
            })
        return rows


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ticks_to_seconds(value: int | None) -> int | None:
    return None if value is None else int(value / 100)
