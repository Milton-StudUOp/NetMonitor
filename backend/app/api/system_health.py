import os
import shutil
from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.discovery import _jobs
from app.api.websocket import manager
from app.database import get_db
from app.models.alert import Alert
from app.models.monitoring_result import MetricAggregate, MonitoringResult
from app.models.platform import AuthSession, NotificationDelivery
from app.services.monitoring_engine import monitoring_engine

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None

router = APIRouter(prefix="/api/system-health", tags=["System health"])

@router.get("")
async def system_health(request: Request, db: AsyncSession = Depends(get_db)):
    started=perf_counter(); await db.execute(text("SELECT 1")); database_latency=round((perf_counter()-started)*1000,2)
    disk=shutil.disk_usage(os.getcwd())
    max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource is not None else None
    counts={}
    for name,model in (("raw_metrics",MonitoringResult),("metric_aggregates",MetricAggregate),("active_alerts",Alert),("notification_deliveries",NotificationDelivery),("sessions",AuthSession)):
        query=select(func.count(model.id))
        if name=="active_alerts": query=query.where(Alert.is_resolved==False)
        counts[name]=(await db.execute(query)).scalar() or 0
    jobs=list(_jobs.values())
    engine={"running":monitoring_engine._running,"cycle_interval_seconds":monitoring_engine._cycle_interval,"last_cycle_started_at":monitoring_engine.last_cycle_started_at,"last_cycle_completed_at":monitoring_engine.last_cycle_completed_at,"last_cycle_duration_seconds":monitoring_engine.last_cycle_duration_seconds,"last_cycle_error":monitoring_engine.last_cycle_error,"completed_cycles":monitoring_engine.completed_cycles,"failed_cycles":monitoring_engine.failed_cycles}
    return {"generated_at":datetime.now(timezone.utc),"status":"DEGRADED" if engine["last_cycle_error"] else "HEALTHY","database":{"dialect":db.bind.dialect.name,"latency_ms":database_latency,"active_url_redacted":True},"monitoring_engine":engine,"storage":{"disk_total_bytes":disk.total,"disk_used_bytes":disk.used,"disk_free_bytes":disk.free,"process_max_rss_kb":max_rss_kb},"counters":counts,"runtime":{"websocket_connections":len(manager.active_connections),"discovery_jobs_running":sum(item["status"]=="RUNNING" for item in jobs),"discovery_jobs_total":len(jobs)}}
