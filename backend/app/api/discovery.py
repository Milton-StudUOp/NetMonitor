import asyncio
import ipaddress
import socket
import uuid
from dataclasses import dataclass
from time import monotonic, perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.interface import Interface, InterfaceStatus
from app.models.platform import AuditLog
from app.schemas.platform import DiscoveredDevice, DiscoveryImportRequest, DiscoveryRequest
from app.services.icmp_monitor import ping_target

router = APIRouter(prefix="/api/discovery", tags=["Network discovery"])
MAX_TARGETS = 1024

# Central backend list; clients only select the TOP_100 mode.
TOP_100_TCP_PORTS = (
    7, 9, 13, 21, 22, 23, 25, 26, 37, 53, 79, 80, 81, 88, 106, 110, 111,
    113, 119, 135, 139, 143, 144, 179, 199, 389, 427, 443, 444, 445, 465,
    513, 514, 515, 543, 544, 548, 554, 587, 631, 646, 873, 990, 993, 995,
    1025, 1026, 1027, 1028, 1029, 1110, 1433, 1720, 1723, 1755, 1900, 2000,
    2001, 2049, 2121, 2717, 3000, 3128, 3306, 3389, 3986, 4899, 5000, 5009,
    5051, 5060, 5101, 5190, 5357, 5432, 5631, 5666, 5800, 5900, 6000, 6001,
    6646, 7070, 8000, 8008, 8009, 8080, 8081, 8443, 8888, 9100, 9999,
    10000, 32768, 49152, 49153, 49154, 49155, 49156, 49157,
)
PROFILE_DEFAULTS = {
    "SAFE": {"timeout": 2.0, "retries": 1, "concurrency": 10, "rate": 20.0},
    "NORMAL": {"timeout": 1.5, "retries": 1, "concurrency": 20, "rate": 50.0},
    "AGGRESSIVE": {"timeout": 1.0, "retries": 0, "concurrency": 50, "rate": 200.0},
}
_jobs: dict[str, dict] = {}


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
            count = int(end) - int(start) + 1
            if start.version != end.version or count < 1: raise ValueError
            if count > MAX_TARGETS: raise HTTPException(400, f"Discovery is limited to {MAX_TARGETS} hosts per scan")
            return [str(ipaddress.ip_address(int(start) + offset)) for offset in range(count)]
        return [str(ipaddress.ip_address(value))]
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, "Target must be a valid IP, CIDR network, or IP range") from exc


@dataclass
class ScanOptions:
    timeout: float
    retries: int
    concurrency: int
    rate: float


class RateLimiter:
    def __init__(self, rate: float):
        self.interval, self.next_time, self.lock = 1 / rate, 0.0, asyncio.Lock()

    async def wait(self):
        async with self.lock:
            now = monotonic()
            if self.next_time > now: await asyncio.sleep(self.next_time - now)
            self.next_time = max(now, self.next_time) + self.interval


def _options(request: DiscoveryRequest) -> ScanOptions:
    defaults = PROFILE_DEFAULTS[request.scan_profile]
    return ScanOptions(request.timeout_seconds or defaults["timeout"], defaults["retries"] if request.retries is None else request.retries, request.concurrency or defaults["concurrency"], request.rate_limit or defaults["rate"])


async def _open_port(ip: str, port: int, options: ScanOptions, limiter: RateLimiter) -> bool:
    for attempt in range(options.retries + 1):
        await limiter.wait()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), options.timeout)
            writer.close(); await writer.wait_closed()
            return True
        except (OSError, asyncio.TimeoutError):
            if attempt == options.retries: return False
    return False


async def _hostname(ip: str) -> str | None:
    try: return (await asyncio.wait_for(asyncio.to_thread(socket.gethostbyaddr, ip), 1.5))[0]
    except (OSError, asyncio.TimeoutError): return None


def _arp_seen(ip: str) -> bool:
    """Consult the Linux neighbour cache populated by ICMP on local IPv4 networks."""
    try:
        with open("/proc/net/arp", encoding="utf-8") as table:
            return any(parts[0] == ip and parts[2] != "0x0" for row in list(table)[1:] if len(parts := row.split()) >= 3)
    except OSError:
        return False


def _guess_type(ports: list[int], model: str | None = None, hostname: str | None = None,
                manufacturer: str | None = None, sys_services: int | None = None) -> str:
    identity = " ".join(filter(None, (model, hostname, manufacturer))).lower().replace("-", " ").replace("_", " ")
    patterns = (
        ("FIREWALL", ("firewall", "fortigate", "fortios", "pfsense", "opnsense", "sonicwall", "pan-os", "checkpoint")),
        ("ACCESS_POINT", ("access point", "wireless ap", "unifi ap", "aironet", "ruckus", "aruba instant")),
        ("RADIO", ("airfiber", "powerbeam", "nanobeam", "rocket m", "wireless bridge", "radio link")),
        ("MEDIA_CONVERTER", ("media converter", "fiber converter", "fibre converter")),
        ("SWITCH", ("switch", "catalyst", "procurve", "arubaos-switch", "routeros crs", "edgeswitch")),
        ("ROUTER", ("router", "routeros", "junos", "ios xe", "vyos", "edge router")),
        ("SERVER", ("linux", "windows", "ubuntu", "debian", "centos", "red hat", "freebsd", "vmware", "proxmox")),
    )
    for device_type, keywords in patterns:
        if any(keyword in identity for keyword in keywords): return device_type
    # SNMP sysServices encodes supported OSI layers. Layer 3 without layer 7 is
    # normally infrastructure; layer 7 strongly suggests a host/server.
    if sys_services is not None:
        if sys_services & 64: return "SERVER"
        if sys_services & 4: return "ROUTER"
        if sys_services & 2: return "SWITCH"
    if 161 in ports or 23 in ports: return "SWITCH"
    if any(port in ports for port in (22, 25, 110, 143, 445, 1433, 3306, 3389, 5432)): return "SERVER"
    if any(port in ports for port in (80, 443, 8080, 8443)): return "SERVER"
    return "OTHER"


async def _snmp_identity(ip: str, request: DiscoveryRequest, timeout: float) -> dict:
    try:
        from pysnmp.hlapi.asyncio import CommunityData, ContextData, ObjectIdentity, ObjectType, SnmpEngine, UdpTransportTarget, UsmUserData, getCmd
        auth = UsmUserData(request.snmp_username or "", request.snmp_auth_key, request.snmp_priv_key) if request.snmp_version == "3" else CommunityData(request.snmp_community or "public", mpModel=1)
        engine = SnmpEngine(); transport = UdpTransportTarget((ip, 161), timeout=timeout, retries=0)
        error, error_status, _, bindings = await asyncio.wait_for(getCmd(engine, auth, transport, ContextData(), ObjectType(ObjectIdentity("1.3.6.1.2.1.1.5.0")), ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0")), ObjectType(ObjectIdentity("1.3.6.1.2.1.1.2.0")), ObjectType(ObjectIdentity("1.3.6.1.2.1.1.7.0"))), timeout + .5)
        if error or error_status or len(bindings) < 2: return {}
        sys_name, description = str(bindings[0][1]), str(bindings[1][1])
        object_id = str(bindings[2][1]) if len(bindings) > 2 else None
        try: sys_services = int(bindings[3][1]) if len(bindings) > 3 else None
        except (TypeError, ValueError): sys_services = None
        vendor = next((name for name in ["Cisco", "Juniper", "Huawei", "MikroTik", "Fortinet", "Ubiquiti", "Aruba", "HPE", "Dell", "Ruckus", "Palo Alto", "SonicWall", "VMware"] if name.lower() in description.lower()), None)
        return {"hostname": sys_name, "snmp_available": True, "manufacturer": vendor, "model": description[:128], "sys_object_id": object_id, "sys_services": sys_services, "interfaces": []}
    except Exception:
        return {}


def _job_view(job: dict) -> dict:
    processed, total = job["hosts_processed"] + job["ports_scanned"], job["total_hosts"] + job["total_port_checks"]
    public = {key: value for key, value in job.items() if key not in {"task", "started_at", "request", "targets"}}
    return public | {"elapsed_seconds": round(perf_counter() - job["started_at"], 1), "progress_percent": round(processed * 100 / total) if total else 0}


async def _run_scan(job: dict):
    request, options = job["request"], _options(job["request"])
    semaphore, limiter, active = asyncio.Semaphore(options.concurrency), RateLimiter(options.rate), []

    async def discover(ip: str):
        async with semaphore:
            started = perf_counter(); ping = {"is_up": False, "latency_ms": None}
            if "ICMP" in request.methods:
                for _ in range(options.retries + 1):
                    ping = await ping_target(ip, count=1, timeout=options.timeout)
                    if ping["is_up"]: break
            snmp = await _snmp_identity(ip, request, options.timeout) if "SNMP" in request.methods else {}
            if ping["is_up"] or snmp or _arp_seen(ip):
                hostname = snmp.get("hostname") or await _hostname(ip)
                active.append(DiscoveredDevice(ip_address=ip, hostname=hostname, status="ONLINE", latency_ms=ping.get("latency_ms") or round((perf_counter() - started) * 1000, 2), snmp_available=bool(snmp), manufacturer=snmp.get("manufacturer"), model=snmp.get("model"), device_type=_guess_type([], snmp.get("model"), hostname, snmp.get("manufacturer"), snmp.get("sys_services")), interfaces=snmp.get("interfaces", [])))
                job["hosts_found"] += 1
            job["hosts_processed"] += 1

    await asyncio.gather(*(discover(ip) for ip in job["targets"]))
    ports = list(TOP_100_TCP_PORTS) if request.port_scan_mode == "TOP_100" else request.ports if request.port_scan_mode == "CUSTOM" else []
    job["stage"], job["total_port_checks"] = ("PORT_SCAN" if ports else "FINALIZING"), len(active) * len(ports)

    async def check(device: DiscoveredDevice, port: int):
        async with semaphore:
            if await _open_port(device.ip_address, port, options, limiter): device.open_ports.append(port)
            job["ports_scanned"] += 1

    await asyncio.gather(*(check(device, port) for device in active for port in ports))
    for device in active:
        device.open_ports.sort()
        inferred_type = _guess_type(device.open_ports, device.model, device.hostname, device.manufacturer)
        if inferred_type != "OTHER": device.device_type = inferred_type
    job["results"] = [device.model_dump() for device in sorted(active, key=lambda item: ipaddress.ip_address(item.ip_address))]
    job["stage"] = job["status"] = "COMPLETED"


async def _execute_job(job: dict):
    try: await _run_scan(job)
    except asyncio.CancelledError: job["status"] = job["stage"] = "CANCELLED"
    except Exception as exc: job["status"] = job["stage"] = "FAILED"; job["error"] = str(exc)
    finally:
        # Discovery credentials are request-scoped and removed as soon as the job ends.
        job["request"] = None


def _new_job(request: DiscoveryRequest) -> dict:
    if request.scan_profile == "AGGRESSIVE" and not get_settings().ALLOW_AGGRESSIVE_DISCOVERY:
        raise HTTPException(403, "Aggressive discovery is disabled. An administrator must enable ALLOW_AGGRESSIVE_DISCOVERY.")
    # Keep the in-memory registry bounded without interrupting active work.
    stale = sorted((item for item in _jobs.values() if item["status"] != "RUNNING"), key=lambda item: item["started_at"])
    for old_job in stale[:max(0, len(_jobs) - 99)]: _jobs.pop(old_job["id"], None)
    targets, identifier = _parse_target(request.target), uuid.uuid4().hex
    job = {"id": identifier, "status": "RUNNING", "stage": "HOST_DISCOVERY", "total_hosts": len(targets), "hosts_processed": 0, "hosts_found": 0, "ports_scanned": 0, "total_port_checks": 0, "results": [], "error": None, "started_at": perf_counter(), "targets": targets, "request": request, "task": None}
    _jobs[identifier] = job
    return job


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def start_scan(request: DiscoveryRequest):
    job = _new_job(request); job["task"] = asyncio.create_task(_execute_job(job))
    return _job_view(job)


@router.get("/jobs/{job_id}")
async def scan_progress(job_id: str):
    if job_id not in _jobs: raise HTTPException(404, "Discovery job not found")
    return _job_view(_jobs[job_id])


@router.post("/jobs/{job_id}/cancel")
async def cancel_scan(job_id: str):
    if job_id not in _jobs: raise HTTPException(404, "Discovery job not found")
    job = _jobs[job_id]
    if job["status"] == "RUNNING":
        job["task"].cancel(); await job["task"]
    return _job_view(job)


@router.post("/scan", response_model=list[DiscoveredDevice])
async def scan_network(request: DiscoveryRequest):
    job = _new_job(request); await _execute_job(job)
    if job["status"] == "FAILED": raise HTTPException(500, job["error"])
    return job["results"]


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_devices(request: DiscoveryImportRequest, db: AsyncSession = Depends(get_db)):
    imported, skipped = [], []
    for candidate in request.devices:
        duplicate = (await db.execute(select(Device).where((Device.ip_address == candidate.ip_address) | (Device.name == candidate.name)))).scalar_one_or_none()
        if duplicate: skipped.append({"ip_address": candidate.ip_address, "reason": "Device name or IP already exists"}); continue
        try: device_type = DeviceType(candidate.device_type)
        except ValueError: device_type = DeviceType.OTHER
        device = Device(name=candidate.name[:128], ip_address=candidate.ip_address, device_type=device_type, location=candidate.location[:128], group_name=candidate.group_name, icon_id=candidate.icon_id, manufacturer=candidate.manufacturer, model=candidate.model, monitoring_method=candidate.monitoring_method, snmp_community=candidate.snmp_community, status=DeviceStatus.ONLINE if candidate.status == "ONLINE" else DeviceStatus.UNKNOWN)
        db.add(device); await db.flush(); imported.append({"id": device.id, "name": device.name, "ip_address": device.ip_address})
        for discovered_interface in candidate.interfaces[:128]:
            try: interface_status = InterfaceStatus(discovered_interface.get("status", "UNKNOWN"))
            except ValueError: interface_status = InterfaceStatus.UNKNOWN
            db.add(Interface(device_id=device.id, interface_name=str(discovered_interface.get("name") or f"if{discovered_interface.get('index')}")[:64], snmp_index=discovered_interface.get("index"), status=interface_status, admin_status=InterfaceStatus.UNKNOWN))
        db.add(AuditLog(action="IMPORT", entity_type="DEVICE", entity_id=str(device.id), summary=f"Device {device.name} imported from network discovery"))
    return {"imported": imported, "skipped": skipped}
