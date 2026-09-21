import os
import shutil
from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.discovery import _jobs
from app.api.websocket import manager
from app.config import get_settings
from app.database import get_db
from app.models.alert import Alert
from app.models.monitoring_result import MetricAggregate, MonitoringResult
from app.models.platform import AuthSession, CollectorLease, NotificationDelivery
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
    descriptor_limit = resource.getrlimit(resource.RLIMIT_NOFILE) if resource is not None else None
    try:
        open_file_descriptors = len(os.listdir("/proc/self/fd"))
    except OSError:
        # /proc is unavailable on Windows and some constrained containers.
        open_file_descriptors = None
    counts={}
    for name,model in (("raw_metrics",MonitoringResult),("metric_aggregates",MetricAggregate),("active_alerts",Alert),("notification_deliveries",NotificationDelivery),("sessions",AuthSession)):
        query=select(func.count(model.id))
        if name=="active_alerts": query=query.where(Alert.is_resolved==False)
        counts[name]=(await db.execute(query)).scalar() or 0
    jobs=list(_jobs.values())
    now = datetime.now(timezone.utc)
    collector_leases = (await db.execute(select(CollectorLease).where(
        CollectorLease.expires_at > now).order_by(CollectorLease.scope).limit(2000)
    )).scalars().all()
    engine={"running":monitoring_engine._running,"collector_enabled":get_settings().COLLECTOR_ENABLED,"collector_id":get_settings().collector_id,"cycle_interval_seconds":monitoring_engine._cycle_interval,"probe_concurrency":monitoring_engine._probe_concurrency,"probe_batch_size":monitoring_engine._probe_batch_size,"last_device_probe_count":monitoring_engine.last_device_probe_count,"claimed_device_probe_count":monitoring_engine.last_claimed_device_probe_count,"deferred_device_probe_count":monitoring_engine.last_deferred_device_probe_count,"last_cycle_started_at":monitoring_engine.last_cycle_started_at,"last_cycle_completed_at":monitoring_engine.last_cycle_completed_at,"last_cycle_duration_seconds":monitoring_engine.last_cycle_duration_seconds,"last_cycle_error":monitoring_engine.last_cycle_error,"completed_cycles":monitoring_engine.completed_cycles,"failed_cycles":monitoring_engine.failed_cycles}
    return {"generated_at":datetime.now(timezone.utc),"status":"DEGRADED" if engine["last_cycle_error"] else "HEALTHY","database":{"dialect":db.bind.dialect.name,"latency_ms":database_latency,"active_url_redacted":True},"monitoring_engine":engine,"storage":{"disk_total_bytes":disk.total,"disk_used_bytes":disk.used,"disk_free_bytes":disk.free,"process_max_rss_kb":max_rss_kb,"open_file_descriptors":open_file_descriptors,"file_descriptor_soft_limit":descriptor_limit[0] if descriptor_limit else None,"file_descriptor_hard_limit":descriptor_limit[1] if descriptor_limit else None},"counters":counts,"runtime":{"websocket_connections":len(manager.active_connections),"discovery_jobs_running":sum(item["status"]=="RUNNING" for item in jobs),"discovery_jobs_total":len(jobs),"active_collector_leases":len(collector_leases),"active_collector_ids":sorted({item.owner_id for item in collector_leases}),"collector_leases":[{"scope":item.scope,"owner_id":item.owner_id,"expires_at":item.expires_at} for item in collector_leases]}}
