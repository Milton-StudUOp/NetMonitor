from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert import Alert, AlertSeverity
from app.models.device import Device
from app.models.link import Link
from app.models.redundancy_group import RedundancyGroup, RedundancyStatus
from app.models.monitoring_result import MonitoringResult

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("")
async def generate_report(
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    if period == "daily":
        start_time = now - timedelta(days=1)
    elif period == "weekly":
        start_time = now - timedelta(days=7)
    else:
        start_time = now - timedelta(days=30)

    # 1. Total devices & links count
    total_devices = (await db.execute(select(func.count(Device.id)))).scalar() or 0
    total_links = (await db.execute(select(func.count(Link.id)))).scalar() or 0

    # 2. Total alerts in period
    alerts_query = select(Alert).where(Alert.created_at >= start_time)
    alerts = (await db.execute(alerts_query)).scalars().all()

    total_failures = len(alerts)
    warning_alerts = sum(1 for a in alerts if a.severity == AlertSeverity.WARNING)
    critical_alerts = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)

    # 3. Redundancy loss events
    redundancy_losses = sum(1 for a in alerts if "Redundância" in a.title or "DEGRADED" in a.message)

    # 4. Average MTTR (Mean Time to Resolve) in minutes
    resolved_alerts = [a for a in alerts if a.is_resolved and a.resolved_at]
    if resolved_alerts:
        total_dt = sum((a.resolved_at - a.created_at).total_seconds() for a in resolved_alerts)
        mttr_minutes = round((total_dt / len(resolved_alerts)) / 60.0, 2)
    else:
        mttr_minutes = 0.0

    # 5. Availability percentage (simulated based on probe history)
    results_query = select(func.count(MonitoringResult.id)).where(MonitoringResult.timestamp >= start_time)
    total_probes = (await db.execute(results_query)).scalar() or 0

    up_probes_query = select(func.count(MonitoringResult.id)).where(
        MonitoringResult.timestamp >= start_time,
        MonitoringResult.status == "UP"
    )
    up_probes = (await db.execute(up_probes_query)).scalar() or 0

    availability_pct = round((up_probes / total_probes) * 100.0, 2) if total_probes > 0 else 100.0

    return {
        "period": period,
        "start_time": start_time.isoformat(),
        "end_time": now.isoformat(),
        "metrics": {
            "availability_pct": availability_pct,
            "total_devices": total_devices,
            "total_links": total_links,
            "total_failures": total_failures,
            "warning_alerts": warning_alerts,
            "critical_alerts": critical_alerts,
            "redundancy_loss_events": redundancy_losses,
            "mttr_minutes": mttr_minutes,
        },
    }
