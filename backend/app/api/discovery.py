import asyncio
import ipaddress
import socket
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.interface import Interface, InterfaceStatus
from app.models.platform import AuditLog
from app.schemas.platform import DiscoveredDevice, DiscoveryImportRequest, DiscoveryRequest
from app.services.icmp_monitor import ping_target

router = APIRouter(prefix="/api/discovery", tags=["Network discovery"])
MAX_TARGETS = 1024


def _parse_target(value: str) -> list[str]:
    value = value.strip()
    try:
        if "/" in value:
            network = ipaddress.ip_network(value, strict=False)
            if network.num_addresses > MAX_TARGETS + 2:
                raise HTTPException(400, f"Discovery is limited to {MAX_TARGETS} hosts per scan")
            return [str(ip) for ip in network.hosts()]
        if "-" in value:
            left, right = (part.strip() for part in value.split("-", 1))
            start, end = ipaddress.ip_address(left), ipaddress.ip_address(right)
            if start.version != end.version or int(end) < int(start):
                raise ValueError
            count = int(end) - int(start) + 1
            if count > MAX_TARGETS: raise HTTPException(400, f"Discovery is limited to {MAX_TARGETS} hosts per scan")
            return [str(ipaddress.ip_address(int(start) + offset)) for offset in range(count)]
        return [str(ipaddress.ip_address(value))]
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, "Target must be a valid IP, CIDR network, or IP range") from exc


async def _open_port(ip: str, port: int, timeout: float) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
        writer.close(); await writer.wait_closed(); return True
    except (OSError, asyncio.TimeoutError):
        return False


async def _hostname(ip: str) -> str | None:
    try: return (await asyncio.wait_for(asyncio.to_thread(socket.gethostbyaddr, ip), 1.5))[0]
    except (OSError, asyncio.TimeoutError): return None


def _guess_type(ports: list[int]) -> str:
    if 161 in ports or 23 in ports: return "SWITCH"
    if 80 in ports or 443 in ports or 8080 in ports or 8443 in ports: return "SERVER"
    return "OTHER"


async def _snmp_identity(ip: str, request: DiscoveryRequest) -> dict:
    try:
        from pysnmp.hlapi.asyncio import (CommunityData, ContextData, ObjectIdentity, ObjectType,
            SnmpEngine, UdpTransportTarget, UsmUserData, getCmd, walkCmd)
        auth = UsmUserData(request.snmp_username or "", request.snmp_auth_key, request.snmp_priv_key) if request.snmp_version == "3" else CommunityData(request.snmp_community or "public", mpModel=1)
        engine = SnmpEngine(); transport = UdpTransportTarget((ip, 161), timeout=request.timeout_seconds, retries=0)
        result = await asyncio.wait_for(getCmd(engine, auth,
            transport, ContextData(),
            ObjectType(ObjectIdentity("1.3.6.1.2.1.1.5.0")), ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))), request.timeout_seconds + .5)
        error, status, _, bindings = result
        if error or status or len(bindings) < 2: return {}
        sys_name, description = str(bindings[0][1]), str(bindings[1][1])
        vendor = next((name for name in ["Cisco", "Juniper", "Huawei", "MikroTik", "Fortinet", "Ubiquiti", "Aruba", "HPE", "Dell"] if name.lower() in description.lower()), None)
        interfaces = {}
        async for walk_error, walk_status, _, bindings in walkCmd(engine, auth, transport, ContextData(),
                ObjectType(ObjectIdentity("1.3.6.1.2.1.2.2.1.2")), lexicographicMode=False, maxRows=128):
            if walk_error or walk_status or not bindings: break
            oid, value = bindings[0]
            index = str(oid).split(".")[-1]; interfaces[index] = {"index": int(index), "name": str(value), "status": "UNKNOWN"}
            if len(interfaces) >= 128: break
        async for walk_error, walk_status, _, bindings in walkCmd(engine, auth, transport, ContextData(),
                ObjectType(ObjectIdentity("1.3.6.1.2.1.2.2.1.8")), lexicographicMode=False, maxRows=128):
            if walk_error or walk_status or not bindings: break
            oid, value = bindings[0]; index = str(oid).split(".")[-1]
            if index in interfaces: interfaces[index]["status"] = {1: "UP", 2: "DOWN", 3: "TESTING"}.get(int(value), "UNKNOWN")
        return {"hostname": sys_name, "snmp_available": True, "manufacturer": vendor, "model": description[:128], "interfaces": list(interfaces.values())}
    except Exception:
        return {}


async def _probe(ip: str, request: DiscoveryRequest, semaphore: asyncio.Semaphore) -> DiscoveredDevice:
    async with semaphore:
        started = perf_counter()
        ping = await ping_target(ip, count=1, timeout=request.timeout_seconds) if "ICMP" in request.methods else {"is_up": False, "latency_ms": None}
        ports = []
        if "TCP" in request.methods:
            valid_ports = sorted(set(port for port in request.ports if 1 <= port <= 65535))[:64]
            checks = await asyncio.gather(*[_open_port(ip, port, request.timeout_seconds) for port in valid_ports])
            ports = [port for port, opened in zip(valid_ports, checks) if opened]
        is_up = ping["is_up"] or bool(ports)
        hostname = await _hostname(ip) if is_up else None
        snmp = await _snmp_identity(ip, request) if "SNMP" in request.methods and (is_up or request.snmp_community or request.snmp_username) else {}
        latency = ping.get("latency_ms") or (round((perf_counter() - started) * 1000, 2) if ports else None)
        is_up = is_up or bool(snmp)
        return DiscoveredDevice(ip_address=ip, hostname=snmp.get("hostname") or hostname, status="ONLINE" if is_up else "OFFLINE",
            latency_ms=latency, open_ports=ports, snmp_available=bool(snmp), manufacturer=snmp.get("manufacturer"),
            model=snmp.get("model"), device_type=_guess_type(ports), interfaces=snmp.get("interfaces", []))


@router.post("/scan", response_model=list[DiscoveredDevice])
async def scan_network(request: DiscoveryRequest):
    targets = _parse_target(request.target)
    methods = {x.upper() for x in request.methods}
    if not methods.issubset({"ICMP", "TCP", "SNMP"}): raise HTTPException(422, "Unsupported discovery method")
    request.methods = list(methods)
    semaphore = asyncio.Semaphore(64)
    results = await asyncio.gather(*[_probe(ip, request, semaphore) for ip in targets])
    return [item for item in results if item.status == "ONLINE"]


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_devices(request: DiscoveryImportRequest, db: AsyncSession = Depends(get_db)):
    imported, skipped = [], []
    for candidate in request.devices:
        duplicate = (await db.execute(select(Device).where((Device.ip_address == candidate.ip_address) | (Device.name == candidate.name)))).scalar_one_or_none()
        if duplicate: skipped.append({"ip_address": candidate.ip_address, "reason": "Device name or IP already exists"}); continue
        try: device_type = DeviceType(candidate.device_type)
        except ValueError: device_type = DeviceType.OTHER
        device = Device(name=candidate.name[:128], ip_address=candidate.ip_address, device_type=device_type,
            location=candidate.location[:128], group_name=candidate.group_name, icon_id=candidate.icon_id,
            manufacturer=candidate.manufacturer, model=candidate.model, monitoring_method=candidate.monitoring_method,
            snmp_community=candidate.snmp_community, status=DeviceStatus.ONLINE if candidate.status == "ONLINE" else DeviceStatus.UNKNOWN)
        db.add(device); await db.flush(); imported.append({"id": device.id, "name": device.name, "ip_address": device.ip_address})
        for discovered_interface in candidate.interfaces[:128]:
            try: interface_status = InterfaceStatus(discovered_interface.get("status", "UNKNOWN"))
            except ValueError: interface_status = InterfaceStatus.UNKNOWN
            db.add(Interface(device_id=device.id, interface_name=str(discovered_interface.get("name") or f"if{discovered_interface.get('index')}")[:64],
                snmp_index=discovered_interface.get("index"), status=interface_status, admin_status=InterfaceStatus.UNKNOWN))
        db.add(AuditLog(action="IMPORT", entity_type="DEVICE", entity_id=str(device.id), summary=f"Device {device.name} imported from network discovery"))
    return {"imported": imported, "skipped": skipped}
