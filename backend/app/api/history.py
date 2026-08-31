from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.monitoring_result import MonitoringResult, MonitoringTargetType
from app.models.device import Device
from app.models.link import Link

router = APIRouter(prefix="/api/history", tags=["History"])


@router.get("/probes")
async def get_probe_history(
    target_type: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns real time-series ICMP/SNMP probe history records from SQLite database.
    """
    query = select(MonitoringResult)
    if target_type:
        query = query.where(MonitoringResult.target_type == target_type)

    results = (await db.execute(query.order_by(MonitoringResult.timestamp.desc()).limit(limit))).scalars().all()

    # Pre-fetch device and link names
    devices = {d.id: d.name for d in (await db.execute(select(Device))).scalars().all()}
    links = {l.id: l.name for l in (await db.execute(select(Link))).scalars().all()}

    history_list = []
    for r in results:
        target_name = "Desconhecido"
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
