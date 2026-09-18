from datetime import datetime, timezone
from fnmatch import fnmatch

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device, DeviceStatus
from app.models.monitoring_provider import (DeviceMonitoringCredential, DiscoveredService,
    MonitoringProfile, ServiceCheckHistory, SystemMetricSnapshot)
from app.schemas.monitoring_provider import MonitoringProfileInput, ServiceMonitoringUpdate
from app.security import decrypt_secret
from app.services.windows_monitoring import WinRMTransport, WindowsMonitoringError, WindowsMonitoringProvider

router = APIRouter(prefix="/api", tags=["Windows monitoring"])


async def _provider(db: AsyncSession, device: Device) -> WindowsMonitoringProvider:
    credential = (await db.execute(select(DeviceMonitoringCredential).where(
        DeviceMonitoringCredential.device_id == device.id, DeviceMonitoringCredential.provider == "WINDOWS",
        DeviceMonitoringCredential.enabled.is_(True)))).scalar_one_or_none()
    if not credential: raise HTTPException(400, "Configure Windows monitoring first")
    password = decrypt_secret(credential.encrypted_password)
    if password is None: raise HTTPException(409, "Stored monitoring credentials cannot be decrypted")
    return WindowsMonitoringProvider(WinRMTransport(device.ip_address, credential.username, password,
        credential.port, credential.use_https, credential.verify_certificate, credential.authentication))


def _service(item: DiscoveredService) -> dict:
    return {key: getattr(item, key) for key in ("id", "device_id", "name", "display_name", "description",
        "service_account", "state", "start_mode", "monitoring_provider", "monitored", "expected_state",
        "check_interval", "failure_threshold", "recovery_threshold", "severity", "notifications_enabled",
        "monitor_state", "last_checked_at", "last_discovered_at")}


@router.get("/services/overview")
async def services_overview(db: AsyncSession = Depends(get_db)):
    services = (await db.execute(select(DiscoveredService).where(
        DiscoveredService.monitored.is_(True)).order_by(DiscoveredService.last_checked_at.desc()))).scalars().all()
    devices = {x.id: x for x in (await db.execute(select(Device))).scalars().all()}
    counts = {state: sum(1 for x in services if x.monitor_state == state)
              for state in ("UP", "DOWN", "SUSPECTED", "RECOVERING", "UNKNOWN")}
    by_device = []
    for device_id in sorted({x.device_id for x in services}):
        items = [x for x in services if x.device_id == device_id]; device = devices.get(device_id)
        if not device: continue
        health = "DOWN" if any(x.monitor_state == "DOWN" for x in items) else (
            "DEGRADED" if any(x.monitor_state in {"SUSPECTED", "RECOVERING", "UNKNOWN"} for x in items) else "UP")
        by_device.append({"device_id": device.id, "device_name": device.name, "ip_address": device.ip_address,
            "device_status": device.status.value, "service_health": health, "total": len(items),
            "down": sum(1 for x in items if x.monitor_state == "DOWN"),
            "degraded": sum(1 for x in items if x.monitor_state in {"SUSPECTED", "RECOVERING", "UNKNOWN"})})
    return {"summary": {"total": len(services), **{k.lower(): v for k, v in counts.items()},
        "devices": len(by_device)}, "devices": by_device,
        "attention": [{**_service(x), "device_name": devices[x.device_id].name} for x in services
            if x.monitor_state in {"DOWN", "SUSPECTED", "RECOVERING", "UNKNOWN"}][:20],
        "recent": [{**_service(x), "device_name": devices[x.device_id].name} for x in services[:20]]}


@router.get("/services/topology")
async def services_topology(db: AsyncSession = Depends(get_db)):
    services = (await db.execute(select(DiscoveredService).where(
        DiscoveredService.monitored.is_(True)).order_by(DiscoveredService.device_id, DiscoveredService.display_name))).scalars().all()
    device_ids = {x.device_id for x in services}
    devices = (await db.execute(select(Device).where(Device.id.in_(device_ids)))).scalars().all() if device_ids else []
    return {"devices": [{"id": x.id, "name": x.name, "ip_address": x.ip_address, "status": x.status.value,
        "location": x.location} for x in devices], "services": [_service(x) for x in services],
        "edges": [{"source": f"device-{x.device_id}", "target": f"service-{x.id}"} for x in services]}


@router.get("/services/inventory")
async def monitored_services_inventory(db: AsyncSession = Depends(get_db)):
    services = (await db.execute(select(DiscoveredService).where(
        DiscoveredService.monitored.is_(True)).order_by(
        DiscoveredService.device_id, DiscoveredService.display_name))).scalars().all()
    device_ids = {x.device_id for x in services}
    devices = {x.id: x for x in (await db.execute(select(Device).where(Device.id.in_(device_ids)))).scalars().all()} if device_ids else {}
    return [{**_service(item), "device_name": devices[item.device_id].name,
        "ip_address": devices[item.device_id].ip_address} for item in services if item.device_id in devices]


@router.post("/devices/{device_id}/services/discover")
async def discover_services(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    if device.status != DeviceStatus.ONLINE: raise HTTPException(409, "Device must be online before discovery")
    provider = await _provider(db, device)
    try: discovered = await provider.discover_services()
    except WindowsMonitoringError as exc: raise HTTPException(409, {"code": exc.code, "message": str(exc)}) from exc
    existing = {x.name: x for x in (await db.execute(select(DiscoveredService).where(
        DiscoveredService.device_id == device_id))).scalars().all()}
    now = datetime.now(timezone.utc)
    for value in discovered:
        item = existing.get(value["name"])
        if not item:
            item = DiscoveredService(device_id=device_id, name=value["name"], display_name=value["display_name"])
            db.add(item)
        for key in ("display_name", "description", "service_account", "state", "start_mode", "monitoring_provider"):
            setattr(item, key, value.get(key))
        item.last_discovered_at = now
    await db.commit()
    return {"device_id": device_id, "discovered": len(discovered), "services": [_service(x) for x in
        (await db.execute(select(DiscoveredService).where(DiscoveredService.device_id == device_id)
            .order_by(DiscoveredService.display_name))).scalars().all()]}


@router.get("/devices/{device_id}/services")
async def list_services(device_id: int, search: str = "", state: str | None = None,
                        start_mode: str | None = None, monitored: bool | None = None,
                        db: AsyncSession = Depends(get_db)):
    query = select(DiscoveredService).where(DiscoveredService.device_id == device_id)
    if search: query = query.where(DiscoveredService.display_name.ilike(f"%{search}%"))
    if state: query = query.where(DiscoveredService.state == state.lower())
    if start_mode: query = query.where(DiscoveredService.start_mode == start_mode.lower())
    if monitored is not None: query = query.where(DiscoveredService.monitored == monitored)
    return [_service(x) for x in (await db.execute(query.order_by(DiscoveredService.display_name))).scalars().all()]


@router.put("/devices/{device_id}/services/monitoring")
async def configure_services(device_id: int, data: ServiceMonitoringUpdate, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(DiscoveredService).where(DiscoveredService.device_id == device_id,
        DiscoveredService.id.in_(data.service_ids)))).scalars().all()
    if len(items) != len(set(data.service_ids)): raise HTTPException(400, "One or more services do not belong to this device")
    now = datetime.now(timezone.utc)
    for item in items:
        item.monitored = data.monitored; item.expected_state = data.expected_state
        item.check_interval = data.check_interval; item.failure_threshold = data.failure_threshold
        item.recovery_threshold = data.recovery_threshold; item.severity = data.severity
        item.notifications_enabled = data.notifications_enabled
        item.next_check_at = now if data.monitored else None
        if not data.monitored: item.monitor_state = "UNKNOWN"
    await db.commit()
    return {"updated": len(items), "monitored": data.monitored}


@router.get("/devices/{device_id}/services/history")
async def service_history(device_id: int, limit: int = Query(200, ge=1, le=1000), db: AsyncSession = Depends(get_db)):
    service_ids = select(DiscoveredService.id).where(DiscoveredService.device_id == device_id)
    rows = (await db.execute(select(ServiceCheckHistory).where(ServiceCheckHistory.service_id.in_(service_ids))
        .order_by(ServiceCheckHistory.checked_at.desc()).limit(limit))).scalars().all()
    return [{"id": x.id, "service_id": x.service_id, "observed_state": x.observed_state,
        "monitor_state": x.monitor_state, "error_code": x.error_code, "response_ms": x.response_ms,
        "checked_at": x.checked_at} for x in rows]


@router.post("/devices/{device_id}/metrics/collect")
async def collect_metrics(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    if device.status != DeviceStatus.ONLINE: raise HTTPException(409, "Device must be online before metrics collection")
    try: values = await (await _provider(db, device)).collect_system_metrics()
    except WindowsMonitoringError as exc: raise HTTPException(409, {"code": exc.code, "message": str(exc)}) from exc
    item = SystemMetricSnapshot(device_id=device_id, cpu_percent=values.get("cpu_percent"),
        memory_percent=values.get("memory_percent"), uptime_seconds=values.get("uptime_seconds"),
        storage=values.get("storage") or [])
    db.add(item); await db.commit(); await db.refresh(item)
    return {"id": item.id, **values, "collected_at": item.collected_at}


@router.get("/devices/{device_id}/metrics")
async def list_metrics(device_id: int, limit: int = Query(100, ge=1, le=1000), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SystemMetricSnapshot).where(SystemMetricSnapshot.device_id == device_id)
        .order_by(SystemMetricSnapshot.collected_at.desc()).limit(limit))).scalars().all()
    return [{"id": x.id, "cpu_percent": x.cpu_percent, "memory_percent": x.memory_percent,
        "uptime_seconds": x.uptime_seconds, "storage": x.storage, "collected_at": x.collected_at} for x in rows]


@router.get("/devices/{device_id}/operational-health")
async def operational_health(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    services = (await db.execute(select(DiscoveredService).where(
        DiscoveredService.device_id == device_id, DiscoveredService.monitored.is_(True)))).scalars().all()
    latest = (await db.execute(select(SystemMetricSnapshot).where(SystemMetricSnapshot.device_id == device_id)
        .order_by(SystemMetricSnapshot.collected_at.desc()).limit(1))).scalar_one_or_none()
    service_state = "DOWN" if any(x.monitor_state == "DOWN" for x in services) else (
        "DEGRADED" if any(x.monitor_state in {"SUSPECTED", "RECOVERING", "UNKNOWN"} for x in services) else "UP")
    return {"device_id": device_id, "availability": device.status.value, "windows_services": service_state,
        "monitored_services": len(services), "cpu": latest.cpu_percent if latest else None,
        "memory": latest.memory_percent if latest else None, "storage": latest.storage if latest else [],
        "operational_state": "DEGRADED" if device.status == DeviceStatus.ONLINE and service_state != "UP" else device.status.value}


@router.get("/monitoring-profiles")
async def list_profiles(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(MonitoringProfile).order_by(MonitoringProfile.name))).scalars().all()


@router.post("/monitoring-profiles", status_code=201)
async def create_profile(data: MonitoringProfileInput, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(MonitoringProfile).where(MonitoringProfile.name == data.name))).scalar_one_or_none():
        raise HTTPException(409, "A monitoring profile with this name already exists")
    item = MonitoringProfile(**data.model_dump()); db.add(item); await db.commit(); await db.refresh(item); return item


@router.post("/devices/{device_id}/monitoring-profiles/{profile_id}/apply")
async def apply_profile(device_id: int, profile_id: int, db: AsyncSession = Depends(get_db)):
    profile = await db.get(MonitoringProfile, profile_id)
    if not profile or not profile.enabled: raise HTTPException(404, "Monitoring profile not found")
    services = (await db.execute(select(DiscoveredService).where(DiscoveredService.device_id == device_id))).scalars().all()
    defaults = {"expected_state": "running", "check_interval": 60, "failure_threshold": 3,
        "recovery_threshold": 2, "severity": "CRITICAL", "notifications_enabled": True, **(profile.defaults or {})}
    matched = [x for x in services if any(fnmatch(x.name.lower(), p.lower()) for p in profile.service_patterns)]
    now = datetime.now(timezone.utc)
    for item in matched:
        item.monitored = True; item.next_check_at = now
        for key in ("expected_state", "check_interval", "failure_threshold", "recovery_threshold", "severity", "notifications_enabled"):
            setattr(item, key, defaults[key])
    await db.commit(); return {"profile": profile.name, "matched_services": len(matched)}
