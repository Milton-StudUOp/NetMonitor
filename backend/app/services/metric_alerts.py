import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.alert import Alert, AlertSeverity
from app.services.notification.dispatcher import dispatch_persisted_notifications


METRIC_LABELS = {"cpu":"CPU usage", "memory":"Memory usage", "storage":"Disk usage"}


def metric_values(values: dict) -> dict[str,float | None]:
    disks = [float(item.get("used_percent", 0)) for item in values.get("storage") or []]
    return {"cpu":values.get("cpu_percent"), "memory":values.get("memory_percent"),
        "storage":max(disks) if disks else None}


async def evaluate_metric_alerts(db, device, values: dict, configuration: dict) -> None:
    thresholds = configuration.get("metric_thresholds") or {}
    enabled_metrics = set(configuration.get("enabled_metrics") or [])
    notifications = bool(configuration.get("metric_notifications_enabled", True))
    now = datetime.now(timezone.utc)
    for key, value in metric_values(values).items():
        policy = thresholds.get(key) or {}
        title = f"{METRIC_LABELS[key]} threshold on {device.name}"
        active = (await db.execute(select(Alert).where(
            Alert.device_id == device.id, Alert.title == title, Alert.is_resolved.is_(False)
        ))).scalar_one_or_none()
        warning, critical = policy.get("warning"), policy.get("critical")
        severity = None
        if key in enabled_metrics and policy.get("enabled", True) and value is not None:
            if critical is not None and value >= float(critical): severity = "CRITICAL"
            elif warning is not None and value >= float(warning): severity = "WARNING"
        if severity:
            message = f"{METRIC_LABELS[key]} is {value:.2f}%; configured {severity.lower()} threshold exceeded."
            if not active:
                active = Alert(severity=AlertSeverity(severity), title=title, message=message,
                    device_id=device.id, root_cause="METRIC_THRESHOLD")
                db.add(active); await db.flush()
                if notifications:
                    asyncio.create_task(dispatch_persisted_notifications(title,message,severity,active.id))
            else:
                active.severity=AlertSeverity(severity); active.message=message
        elif active:
            active.is_resolved=True; active.resolved_at=now
