import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert import Alert, AlertSeverity
from app.models.device import Device
from app.models.link import Link
from app.models.monitoring_result import MetricAggregate, MonitoringResult, MonitoringStatus, MonitoringTargetType

router = APIRouter(prefix="/api/reports", tags=["Reports"])
PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "quarterly": 90}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _range(period: str, start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    range_end = _as_utc(end) if end else datetime.now(timezone.utc)
    if start: range_start = _as_utc(start)
    elif period in PERIOD_DAYS: range_start = range_end - timedelta(days=PERIOD_DAYS[period])
    else: raise HTTPException(422, "Period must be daily, weekly, monthly, or quarterly")
    if range_start >= range_end: raise HTTPException(422, "Start date must be earlier than end date")
    return range_start, range_end


async def _report_data(db: AsyncSession, period: str, start: datetime | None, end: datetime | None,
                       target_type: str | None, target_id: int | None, severity: AlertSeverity | None,
                       probe_status: MonitoringStatus | None, include_probe_rows: bool = False) -> dict:
    range_start, range_end = _range(period, start, end)
    alert_query = select(Alert).where(Alert.created_at >= range_start, Alert.created_at <= range_end)
    source_columns = {"DEVICE": Alert.device_id, "LINK": Alert.link_id, "REDUNDANCY_GROUP": Alert.redundancy_group_id}
    if target_type in source_columns:
        alert_column = source_columns[target_type]
        alert_query = alert_query.where(alert_column.is_not(None))
        if target_id is not None: alert_query = alert_query.where(alert_column == target_id)
    elif target_id is not None:
        alert_query = alert_query.where(or_(Alert.device_id == target_id, Alert.link_id == target_id, Alert.redundancy_group_id == target_id))
    if severity: alert_query = alert_query.where(Alert.severity == severity)
    alerts = (await db.execute(alert_query.order_by(Alert.created_at.desc()))).scalars().all()

    probe_query = select(MonitoringResult).where(MonitoringResult.timestamp >= range_start, MonitoringResult.timestamp <= range_end)
    if target_type in {item.value for item in MonitoringTargetType}: probe_query = probe_query.where(MonitoringResult.target_type == target_type)
    if target_id is not None: probe_query = probe_query.where(MonitoringResult.target_id == target_id)
    if probe_status: probe_query = probe_query.where(MonitoringResult.status == probe_status)
    probes = (await db.execute(probe_query.order_by(MonitoringResult.timestamp.desc()))).scalars().all()

    aggregate_query = select(MetricAggregate).where(
        MetricAggregate.granularity == "DAILY",
        MetricAggregate.bucket_start >= range_start,
        MetricAggregate.bucket_start <= range_end,
    )
    if target_type in {item.value for item in MonitoringTargetType}:
        aggregate_query = aggregate_query.where(MetricAggregate.target_type == target_type)
    if target_id is not None:
        aggregate_query = aggregate_query.where(MetricAggregate.target_id == target_id)
    aggregates = (await db.execute(aggregate_query)).scalars().all()

    total_devices = (await db.execute(select(func.count(Device.id)))).scalar() or 0
    total_links = (await db.execute(select(func.count(Link.id)))).scalar() or 0
    raw_up_probes = sum((item.status.value if hasattr(item.status, "value") else str(item.status)) == "UP" for item in probes)
    aggregate_samples = sum(item.sample_count for item in aggregates)
    aggregate_up_probes = sum(item.up_count for item in aggregates)
    total_probes = len(probes) + aggregate_samples
    up_probes = raw_up_probes + aggregate_up_probes
    resolved = [item for item in alerts if item.is_resolved and item.resolved_at]
    resolution_seconds = [(_as_utc(item.resolved_at) - _as_utc(item.created_at)).total_seconds() for item in resolved]
    critical = sum(item.severity == AlertSeverity.CRITICAL for item in alerts)
    warning = sum(item.severity == AlertSeverity.WARNING for item in alerts)
    redundancy = sum(item.redundancy_group_id is not None for item in alerts)
    observation_hours = (range_end - range_start).total_seconds() / 3600
    return {
        "period": period, "start_time": range_start.isoformat(), "end_time": range_end.isoformat(),
        "filters": {"target_type": target_type, "target_id": target_id, "severity": severity.value if severity else None, "probe_status": probe_status.value if probe_status else None},
        "metrics": {"availability_pct": round(up_probes * 100 / total_probes, 2) if total_probes else None, "total_devices": total_devices, "total_links": total_links, "total_failures": len(alerts), "warning_alerts": warning, "critical_alerts": critical, "redundancy_loss_events": redundancy, "mttr_minutes": round(sum(resolution_seconds) / len(resolution_seconds) / 60, 2) if resolution_seconds else None, "mtbf_hours": round(observation_hours / len(alerts), 2) if alerts else None, "total_probes": total_probes},
        "alerts": [{"id": item.id, "created_at": item.created_at.isoformat(), "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None, "severity": item.severity.value, "title": item.title, "message": item.message, "status": "RESOLVED" if item.is_resolved else "ACTIVE", "device_id": item.device_id, "link_id": item.link_id, "redundancy_group_id": item.redundancy_group_id} for item in alerts],
        "probes": [{"id": item.id, "timestamp": item.timestamp.isoformat(), "target_type": item.target_type.value, "target_id": item.target_id, "status": item.status.value, "latency_ms": item.latency_ms, "packet_loss_pct": item.packet_loss_pct} for item in probes] if include_probe_rows else [],
    }


@router.get("")
async def generate_report(period: str = "daily", start: datetime | None = None, end: datetime | None = None,
                          target_type: str | None = Query(default=None, pattern="^(DEVICE|LINK|REDUNDANCY_GROUP)$"),
                          target_id: int | None = None, severity: AlertSeverity | None = None,
                          probe_status: MonitoringStatus | None = None, db: AsyncSession = Depends(get_db)):
    return await _report_data(db, period, start, end, target_type, target_id, severity, probe_status)


@router.get("/export")
async def export_report(period: str = "daily", start: datetime | None = None, end: datetime | None = None,
                        target_type: str | None = Query(default=None, pattern="^(DEVICE|LINK|REDUNDANCY_GROUP)$"),
                        target_id: int | None = None, severity: AlertSeverity | None = None,
                        probe_status: MonitoringStatus | None = None, db: AsyncSession = Depends(get_db)):
    report = await _report_data(db, period, start, end, target_type, target_id, severity, probe_status, include_probe_rows=True)
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Network Monitor filtered report"]); writer.writerow(["Start", report["start_time"]]); writer.writerow(["End", report["end_time"]])
    writer.writerow([]); writer.writerow(["Metric", "Value"])
    for key, value in report["metrics"].items(): writer.writerow([key, "" if value is None else value])
    writer.writerow([]); writer.writerow(["ALERTS"]); writer.writerow(["Created", "Resolved", "Severity", "Status", "Title", "Message", "Device ID", "Link ID", "Redundancy Group ID"])
    for item in report["alerts"]: writer.writerow([item["created_at"], item["resolved_at"] or "", item["severity"], item["status"], item["title"], item["message"], item["device_id"] or "", item["link_id"] or "", item["redundancy_group_id"] or ""])
    writer.writerow([]); writer.writerow(["PROBES"]); writer.writerow(["Timestamp", "Target Type", "Target ID", "Status", "Latency ms", "Packet Loss %"])
    for item in report["probes"]: writer.writerow([item["timestamp"], item["target_type"], item["target_id"], item["status"], item["latency_ms"] if item["latency_ms"] is not None else "", item["packet_loss_pct"] if item["packet_loss_pct"] is not None else ""])
    filename = f"network-monitor-report-{report['start_time'][:10]}-{report['end_time'][:10]}.csv"
    return StreamingResponse(iter([output.getvalue().encode("utf-8-sig")]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
