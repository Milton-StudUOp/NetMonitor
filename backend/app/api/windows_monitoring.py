from datetime import datetime, timedelta, timezone
from math import ceil
from fnmatch import fnmatch

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device, DeviceStatus
from app.models.monitoring_provider import (DeviceCapability, DeviceMonitoringCredential, DiscoveredService,
    MonitoringProfile, ServiceCheckHistory, SystemMetricSnapshot)
from app.schemas.monitoring_provider import MonitoringProfileInput, ServiceMonitoringUpdate
from app.security import decrypt_secret
from app.services.windows_monitoring import WinRMTransport, WindowsMonitoringError, WindowsMonitoringProvider

router = APIRouter(prefix="/api", tags=["Windows monitoring"])
SERVICE_PERIOD_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30, "90d": 24 * 90}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _metric_snapshot(item: SystemMetricSnapshot) -> dict:
    details = item.storage if isinstance(item.storage, dict) else {"disks": item.storage or []}
    return {"id": item.id, "cpu_percent": item.cpu_percent, "memory_percent": item.memory_percent,
        "uptime_seconds": item.uptime_seconds, "storage": details.get("disks", []),
        "network_interfaces": details.get("network_interfaces", []),
        "network_adapters": details.get("network_adapters", []), "processes": details.get("processes", []),
        "system_information": details.get("system_information", {}), "events": details.get("events", []),
        "collected_at": item.collected_at}


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
    result = {key: getattr(item, key) for key in ("id", "device_id", "name", "display_name", "description",
        "service_account", "state", "start_mode", "monitoring_provider", "monitored", "expected_state",
        "check_interval", "failure_threshold", "recovery_threshold", "severity", "notifications_enabled",
        "monitor_state", "last_checked_at", "last_discovered_at")}
    if result["monitor_state"] == "SUSPECTED":
        result["monitor_state"] = "DOWN"
    result["failure_threshold"] = 1
    return result


@router.get("/services/overview")
async def services_overview(db: AsyncSession = Depends(get_db)):
    services = (await db.execute(select(DiscoveredService).where(
        DiscoveredService.monitored.is_(True)).order_by(DiscoveredService.last_checked_at.desc()))).scalars().all()
    devices = {x.id: x for x in (await db.execute(select(Device))).scalars().all()}
    state_of = lambda item: "DOWN" if item.monitor_state == "SUSPECTED" else item.monitor_state
    counts = {state: sum(1 for x in services if state_of(x) == state)
              for state in ("UP", "DOWN", "RECOVERING", "UNKNOWN")}
    by_device = []
    for device_id in sorted({x.device_id for x in services}):
        items = [x for x in services if x.device_id == device_id]; device = devices.get(device_id)
        if not device: continue
        health = "DOWN" if any(state_of(x) == "DOWN" for x in items) else (
            "DEGRADED" if any(state_of(x) in {"RECOVERING", "UNKNOWN"} for x in items) else "UP")
        by_device.append({"device_id": device.id, "device_name": device.name, "ip_address": device.ip_address,
            "device_status": device.status.value, "service_health": health, "total": len(items),
            "down": sum(1 for x in items if state_of(x) == "DOWN"),
            "degraded": sum(1 for x in items if state_of(x) in {"RECOVERING", "UNKNOWN"})})
    return {"summary": {"total": len(services), **{k.lower(): v for k, v in counts.items()},
        "devices": len(by_device)}, "devices": by_device,
        "attention": [{**_service(x), "device_name": devices[x.device_id].name} for x in services
            if state_of(x) in {"DOWN", "RECOVERING", "UNKNOWN"}][:20],
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


@router.get("/services/{service_id}/analytics")
async def service_analytics(service_id: int, period: str = Query("24h"), db: AsyncSession = Depends(get_db)):
    if period not in SERVICE_PERIOD_HOURS:
        raise HTTPException(422, "Period must be one of: 24h, 7d, 30d, 90d")
    service = await db.get(DiscoveredService, service_id)
    if not service: raise HTTPException(404, "Service not found")
    device = await db.get(Device, service.device_id)
    end = datetime.now(timezone.utc); start = end - timedelta(hours=SERVICE_PERIOD_HOURS[period])
    records = (await db.execute(select(ServiceCheckHistory).where(ServiceCheckHistory.service_id == service_id,
        ServiceCheckHistory.checked_at >= start, ServiceCheckHistory.checked_at <= end)
        .order_by(ServiceCheckHistory.checked_at))).scalars().all()
    bucket_seconds = max(60, ceil((end - start).total_seconds() / 240)); buckets = {}
    for record in records:
        bucket = int((_utc(record.checked_at) - start).total_seconds() // bucket_seconds)
        buckets.setdefault(bucket, []).append(record)
    rank = {"UNKNOWN": 0, "UP": 1, "RECOVERING": 2, "SUSPECTED": 3, "DOWN": 4}
    series = []
    for bucket, samples in sorted(buckets.items()):
        status = max((x.monitor_state for x in samples), key=lambda x: rank.get(x, 0))
        if status == "SUSPECTED": status = "DOWN"
        times = [x.response_ms for x in samples if x.response_ms is not None]
        healthy = sum(x.observed_state == service.expected_state and not x.error_code for x in samples)
        series.append({"timestamp": (start + timedelta(seconds=bucket * bucket_seconds)).isoformat(),
            "status": status, "availability_pct": round(healthy * 100 / len(samples), 2),
            "response_ms": round(sum(times) / len(times), 2) if times else None, "samples": len(samples)})
    outages = []; outage_start = None; previous = None; failures = recoveries = 0
    for record in records:
        timestamp = _utc(record.checked_at); state = "DOWN" if record.monitor_state == "SUSPECTED" else record.monitor_state
        if state == "DOWN" and previous != "DOWN":
            failures += 1
            if outage_start is None: outage_start = timestamp
        if previous in {"DOWN", "RECOVERING"} and state == "UP": recoveries += 1
        if outage_start and state == "UP":
            outages.append({"started_at": outage_start.isoformat(), "ended_at": timestamp.isoformat(),
                "duration_seconds": max(0, round((timestamp - outage_start).total_seconds())), "ongoing": False})
            outage_start = None
        previous = state
    if outage_start:
        ongoing = service.monitor_state == "DOWN"
        stopped = end if ongoing else min(end, _utc(service.last_checked_at) if service.last_checked_at else end)
        outages.append({"started_at": outage_start.isoformat(), "ended_at": None if ongoing else stopped.isoformat(),
            "duration_seconds": max(0, round((stopped - outage_start).total_seconds())), "ongoing": ongoing})
    known = [x for x in records if not x.error_code and x.observed_state != "unknown"]
    successful = sum(x.observed_state == service.expected_state for x in known)
    response_times = [x.response_ms for x in records if x.response_ms is not None]
    return {"service": {**_service(service), "device_name": device.name if device else f"Device #{service.device_id}",
            "ip_address": device.ip_address if device else None},
        "period": {"start": start.isoformat(), "end": end.isoformat(), "bucket_seconds": bucket_seconds},
        "summary": {"availability_pct": round(successful * 100 / len(known), 2) if known else None,
            "total_checks": len(records), "successful_checks": successful,
            "average_response_ms": round(sum(response_times) / len(response_times), 2) if response_times else None,
            "maximum_response_ms": round(max(response_times), 2) if response_times else None,
            "failure_events": failures, "recovery_events": recoveries,
            "communication_errors": sum(bool(x.error_code) for x in records),
            "downtime_seconds": sum(x["duration_seconds"] for x in outages), "outage_count": len(outages)},
        "series": series, "outages": list(reversed(outages)),
        "history": [{"id": x.id, "checked_at": x.checked_at, "observed_state": x.observed_state,
            "monitor_state": x.monitor_state, "response_ms": x.response_ms, "error_code": x.error_code}
            for x in reversed(records[-100:])]}


@router.post("/devices/{device_id}/metrics/collect")
async def collect_metrics(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    if device.status != DeviceStatus.ONLINE: raise HTTPException(409, "Device must be online before metrics collection")
    try: values = await (await _provider(db, device)).collect_system_metrics()
    except WindowsMonitoringError as exc: raise HTTPException(409, {"code": exc.code, "message": str(exc)}) from exc
    details = {key: values.get(key) for key in ("network_interfaces", "network_adapters", "processes",
        "system_information", "events")}
    item = SystemMetricSnapshot(device_id=device_id, cpu_percent=values.get("cpu_percent"),
        memory_percent=values.get("memory_percent"), uptime_seconds=values.get("uptime_seconds"),
        storage={"disks": values.get("storage") or [], **details})
    db.add(item); await db.commit(); await db.refresh(item)
    return _metric_snapshot(item)


@router.get("/devices/{device_id}/metrics")
async def list_metrics(device_id: int, limit: int = Query(100, ge=1, le=1000), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SystemMetricSnapshot).where(SystemMetricSnapshot.device_id == device_id)
        .order_by(SystemMetricSnapshot.collected_at.desc()).limit(limit))).scalars().all()
    return [_metric_snapshot(x) for x in rows]


@router.get("/devices/{device_id}/metrics/capabilities")
async def metric_capabilities(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    try: capabilities = await (await _provider(db, device)).discover_metric_capabilities()
    except WindowsMonitoringError as exc: raise HTTPException(409, {"code": exc.code, "message": str(exc)}) from exc
    saved = (await db.execute(select(DeviceCapability).where(DeviceCapability.device_id == device_id,
        DeviceCapability.provider == "WINDOWS"))).scalar_one_or_none()
    enabled = (saved.diagnostics or {}).get("enabled_metrics", []) if saved else []
    return {"device_id": device.id, "device_name": device.name, "capabilities": capabilities,
        "enabled_metrics": enabled}


@router.put("/devices/{device_id}/metrics/configuration")
async def configure_metrics(device_id: int, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    available = await (await _provider(db, device)).discover_metric_capabilities()
    selected = list(dict.fromkeys(payload.get("enabled_metrics") or []))
    invalid = [key for key in selected if key not in available or not available[key]["supported"]]
    if invalid: raise HTTPException(400, f"Unsupported metrics: {', '.join(invalid)}")
    item = (await db.execute(select(DeviceCapability).where(DeviceCapability.device_id == device_id,
        DeviceCapability.provider == "WINDOWS"))).scalar_one_or_none()
    if not item:
        item = DeviceCapability(device_id=device_id, provider="WINDOWS", platform="windows"); db.add(item)
    item.diagnostics = {**(item.diagnostics or {}), "enabled_metrics": selected}
    await db.commit()
    return {"device_id": device_id, "enabled_metrics": selected}


@router.get("/metrics/overview")
async def metrics_overview(db: AsyncSession = Depends(get_db)):
    devices = (await db.execute(select(Device).order_by(Device.name))).scalars().all()
    result = []
    for device in devices:
        latest = (await db.execute(select(SystemMetricSnapshot).where(SystemMetricSnapshot.device_id == device.id)
            .order_by(SystemMetricSnapshot.collected_at.desc()).limit(1))).scalar_one_or_none()
        if latest: result.append({"device": {"id": device.id, "name": device.name,
            "ip_address": device.ip_address, "status": device.status.value}, "latest": _metric_snapshot(latest)})
    return result


@router.get("/devices/{device_id}/operational-health")
async def operational_health(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    services = (await db.execute(select(DiscoveredService).where(
        DiscoveredService.device_id == device_id, DiscoveredService.monitored.is_(True)))).scalars().all()
    latest = (await db.execute(select(SystemMetricSnapshot).where(SystemMetricSnapshot.device_id == device_id)
        .order_by(SystemMetricSnapshot.collected_at.desc()).limit(1))).scalar_one_or_none()
    service_state = "DOWN" if any(x.monitor_state in {"DOWN", "SUSPECTED"} for x in services) else (
        "DEGRADED" if any(x.monitor_state in {"RECOVERING", "UNKNOWN"} for x in services) else "UP")
    return {"device_id": device_id, "availability": device.status.value, "windows_services": service_state,
        "monitored_services": len(services), "cpu": latest.cpu_percent if latest else None,
        "memory": latest.memory_percent if latest else None,
        "storage": (_metric_snapshot(latest)["storage"] if latest else []),
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
    defaults = {"expected_state": "running", "check_interval": 60, "failure_threshold": 1,
        "recovery_threshold": 2, "severity": "CRITICAL", "notifications_enabled": True, **(profile.defaults or {})}
    defaults["failure_threshold"] = 1
    matched = [x for x in services if any(fnmatch(x.name.lower(), p.lower()) for p in profile.service_patterns)]
    now = datetime.now(timezone.utc)
    for item in matched:
        item.monitored = True; item.next_check_at = now
        for key in ("expected_state", "check_interval", "failure_threshold", "recovery_threshold", "severity", "notifications_enabled"):
            setattr(item, key, defaults[key])
    await db.commit(); return {"profile": profile.name, "matched_services": len(matched)}
