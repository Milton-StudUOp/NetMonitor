from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.monitoring_result import MonitoringResult, MonitoringTargetType
from app.models.device import Device
from app.models.link import Link

router = APIRouter(prefix="/api/history", tags=["History"])

PERIOD_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30, "90d": 24 * 90}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _build_device_analytics(device: Device, records: list[MonitoringResult], start: datetime, end: datetime) -> dict:
    records = sorted((record for record in records if record.timestamp), key=lambda record: record.timestamp)
    bucket_seconds = max(60, ceil((end - start).total_seconds() / 240))
    buckets: dict[int, list[MonitoringResult]] = {}
    for record in records:
        bucket = int((_utc(record.timestamp) - start).total_seconds() // bucket_seconds)
        buckets.setdefault(bucket, []).append(record)

    points = []
    for bucket, samples in sorted(buckets.items()):
        latencies = [item.latency_ms for item in samples if item.latency_ms is not None]
        losses = [item.packet_loss_pct for item in samples if item.packet_loss_pct is not None]
        statuses = [item.status.value if hasattr(item.status, "value") else str(item.status) for item in samples]
        status_value = "DOWN" if "DOWN" in statuses else "DEGRADED" if "DEGRADED" in statuses else statuses[-1]
        points.append({
            "timestamp": (start + timedelta(seconds=bucket * bucket_seconds)).isoformat(),
            "status": status_value,
            "availability": 0 if status_value == "DOWN" else 1,
            "latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "packet_loss_pct": round(sum(losses) / len(losses), 2) if losses else None,
            "samples": len(samples),
        })

    outages, outage_start = [], None
    for record in records:
        status_value = record.status.value if hasattr(record.status, "value") else str(record.status)
        timestamp = _utc(record.timestamp)
        if status_value == "DOWN" and outage_start is None:
            outage_start = timestamp
        elif status_value != "DOWN" and outage_start is not None:
            outages.append({"started_at": outage_start.isoformat(), "ended_at": timestamp.isoformat(), "duration_seconds": max(0, round((timestamp - outage_start).total_seconds())), "ongoing": False})
            outage_start = None
    current_status = device.status.value if hasattr(device.status, "value") else str(device.status)
    currently_unavailable = current_status in {"OFFLINE", "DOWN"}
    if outage_start is not None and currently_unavailable:
        outages.append({"started_at": outage_start.isoformat(), "ended_at": None, "duration_seconds": max(0, round((end - outage_start).total_seconds())), "ongoing": True})
    elif outage_start is not None:
        recovered_at = _utc(device.updated_at) if getattr(device, "updated_at", None) else end
        recovered_at = min(end, max(outage_start, recovered_at))
        outages.append({"started_at": outage_start.isoformat(), "ended_at": recovered_at.isoformat(), "duration_seconds": max(0, round((recovered_at - outage_start).total_seconds())), "ongoing": False})
    elif currently_unavailable:
        status_changed_at = _utc(device.updated_at) if getattr(device, "updated_at", None) else (max((_utc(record.timestamp) for record in records), default=end))
        outage_start = max(start, min(status_changed_at, end))
        outages.append({"started_at": outage_start.isoformat(), "ended_at": None, "duration_seconds": max(0, round((end - outage_start).total_seconds())), "ongoing": True})

    statuses = [record.status.value if hasattr(record.status, "value") else str(record.status) for record in records]
    known = [value for value in statuses if value != "UNKNOWN"]
    available = sum(value in {"UP", "DEGRADED"} for value in known)
    latencies = [record.latency_ms for record in records if record.latency_ms is not None]
    losses = [record.packet_loss_pct for record in records if record.packet_loss_pct is not None]
    total_downtime = sum(outage["duration_seconds"] for outage in outages)
    return {
        "device": {"id": device.id, "name": device.name, "ip_address": device.ip_address, "device_type": device.device_type.value if hasattr(device.device_type, "value") else str(device.device_type), "status": device.status.value if hasattr(device.status, "value") else str(device.status), "location": device.location, "manufacturer": device.manufacturer, "model": device.model},
        "period": {"start": start.isoformat(), "end": end.isoformat(), "bucket_seconds": bucket_seconds},
        "summary": {"availability_pct": round(available * 100 / len(known), 2) if known else None, "total_probes": len(records), "successful_probes": available, "outage_count": len(outages), "downtime_seconds": total_downtime, "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None, "maximum_latency_ms": round(max(latencies), 2) if latencies else None, "average_packet_loss_pct": round(sum(losses) / len(losses), 2) if losses else None},
        "series": points,
        "outages": list(reversed(outages)),
    }


@router.get("/probes")
async def get_probe_history(
    response: Response,
    target_type: Optional[str] = Query(default=None, pattern="^(DEVICE|LINK|INTERFACE|SERVICE|REDUNDANCY_GROUP)$"),
    target_id: Optional[int] = None,
    status: Optional[str] = Query(default=None, pattern="^(UP|DOWN|DEGRADED|UNKNOWN)$"),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    search: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=100, le=500),
    page: int = Query(default=1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns real time-series ICMP/SNMP probe history records from SQLite database.
    """
    query = select(MonitoringResult)
    if target_type:
        query = query.where(MonitoringResult.target_type == target_type)
    if target_id is not None: query = query.where(MonitoringResult.target_id == target_id)
    if status: query = query.where(MonitoringResult.status == status)
    if start: query = query.where(MonitoringResult.timestamp >= start)
    if end: query = query.where(MonitoringResult.timestamp <= end)
    if search:
        term = f"%{search.strip()}%"
        device_ids = select(Device.id).where(or_(Device.name.ilike(term), Device.ip_address.ilike(term)))
        link_ids = select(Link.id).where(Link.name.ilike(term))
        query = query.where(or_(
            (MonitoringResult.target_type == MonitoringTargetType.DEVICE) & MonitoringResult.target_id.in_(device_ids),
            (MonitoringResult.target_type == MonitoringTargetType.LINK) & MonitoringResult.target_id.in_(link_ids),
        ))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    results = (await db.execute(query.order_by(MonitoringResult.timestamp.desc()).offset((page-1)*limit).limit(limit))).scalars().all()

    # Pre-fetch device and link names
    devices = {d.id: d.name for d in (await db.execute(select(Device))).scalars().all()}
    links = {l.id: l.name for l in (await db.execute(select(Link))).scalars().all()}

    history_list = []
    for r in results:
        target_name = "Unknown"
        if r.target_type == MonitoringTargetType.DEVICE:
            target_name = devices.get(r.target_id, f"Device #{r.target_id}")
        elif r.target_type == MonitoringTargetType.LINK:
            target_name = links.get(r.target_id, f"Link #{r.target_id}")

        history_list.append({
            "id": r.id,
            "target_type": r.target_type.value if hasattr(r.target_type, 'value') else str(r.target_type),
            "target_id": r.target_id,
            "target_name": target_name,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
            "latency_ms": r.latency_ms,
            "packet_loss_pct": r.packet_loss_pct,
        })

    return history_list


@router.get("/devices/{device_id}/analytics")
async def get_device_analytics(
    device_id: int,
    period: str = Query(default="24h"),
    db: AsyncSession = Depends(get_db),
):
    if period not in PERIOD_HOURS:
        raise HTTPException(status_code=422, detail="Period must be one of: 24h, 7d, 30d, 90d")
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=PERIOD_HOURS[period])
    query = select(MonitoringResult).where(
        MonitoringResult.target_type == MonitoringTargetType.DEVICE,
        MonitoringResult.target_id == device_id,
        MonitoringResult.timestamp >= start,
        MonitoringResult.timestamp <= end,
    ).order_by(MonitoringResult.timestamp)
    records = (await db.execute(query)).scalars().all()
    return _build_device_analytics(device, records, start, end)
