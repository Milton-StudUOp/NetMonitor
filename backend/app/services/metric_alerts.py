from datetime import datetime, timezone

from sqlalchemy import select

from app.models.alert import Alert, AlertSeverity

METRIC_LABELS = {"cpu": "CPU usage", "memory": "Memory usage", "storage": "Disk usage"}
INTERFACE_DOWN_ROOT_CAUSE = "INTERFACE_DOWN"


def _interface_state(row: dict) -> str:
    """Normalise the equivalent state fields returned by every provider."""
    raw = row.get("oper_status", row.get("status", "unknown"))
    return str(raw or "unknown").strip().upper().replace(" ", "_")


def _interface_name(row: dict) -> str:
    value = row.get("name") or row.get("description") or row.get("index")
    return str(value or "unnamed interface").strip()[:128]


def metric_values(values: dict) -> dict[str,float | None]:
    disks = [float(item.get("used_percent", 0)) for item in values.get("storage") or []]
    return {"cpu":values.get("cpu_percent"), "memory":values.get("memory_percent"),
        "storage":max(disks) if disks else None}


async def evaluate_metric_alerts(
    db, device, values: dict, configuration: dict
) -> list[tuple[str, str, str, int, bool]]:
    """Persist metric and interface alert state, returning post-commit deliveries.

    Network interface state is intentionally evaluated here instead of in a UI
    request: all providers persist their selected interface metrics through
    this path, so a DOWN and its subsequent UP recovery produce exactly one
    durable incident and can reach every configured notification channel.
    """
    thresholds = configuration.get("metric_thresholds") or {}
    enabled_metrics = set(configuration.get("enabled_metrics") or [])
    notifications = bool(configuration.get("metric_notifications_enabled", True))
    now = datetime.now(timezone.utc)
    pending = []
    for key, value in metric_values(values).items():
        policy = thresholds.get(key) or {}
        title = f"{METRIC_LABELS[key]} threshold on {device.name}"
        active = (await db.execute(select(Alert).where(
            Alert.device_id == device.id, Alert.title == title, Alert.is_resolved.is_(False)
        ).limit(1))).scalar_one_or_none()
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
                    pending.append((title, message, severity, active.id, False))
            else:
                active.severity=AlertSeverity(severity); active.message=message
        elif active:
            active.is_resolved=True; active.resolved_at=now
            if notifications:
                pending.append((title, f"{METRIC_LABELS[key]} returned to the configured normal range.",
                                active.severity.value, active.id, True))

    interface_monitoring_enabled = "network_interfaces" in enabled_metrics
    if not interface_monitoring_enabled:
        return pending

    for row in values.get("network_interfaces") or []:
        if not isinstance(row, dict):
            continue
        name = _interface_name(row)
        title = f"Interface down: {name} on {device.name}"[:256]
        active = (await db.execute(select(Alert).where(
            Alert.device_id == device.id,
            Alert.title == title,
            Alert.root_cause == INTERFACE_DOWN_ROOT_CAUSE,
            Alert.is_resolved.is_(False),
        ).limit(1))).scalar_one_or_none()
        state = _interface_state(row)
        if state == "DOWN":
            message = f"Interface {name} on {device.name} is operationally DOWN."
            if active is None:
                active = Alert(
                    severity=AlertSeverity.CRITICAL,
                    title=title,
                    message=message,
                    device_id=device.id,
                    root_cause=INTERFACE_DOWN_ROOT_CAUSE,
                )
                db.add(active)
                await db.flush()
                if notifications:
                    pending.append((title, message, AlertSeverity.CRITICAL.value, active.id, False))
            else:
                active.severity = AlertSeverity.CRITICAL
                active.message = message
        elif state == "UP" and active is not None:
            active.is_resolved = True
            active.resolved_at = now
            if notifications:
                pending.append((title, f"Interface {name} on {device.name} recovered and is operationally UP.",
                                active.severity.value, active.id, True))
    return pending


async def resolve_disabled_metric_alerts(db, device_id: int, configuration: dict) -> int:
    """Resolve active metric-threshold incidents removed from a device policy.

    Policy updates must take effect immediately; waiting for the next collector
    pass leaves a stale active incident visible and can be mistaken for a new
    threshold notification.
    """
    thresholds = configuration.get("metric_thresholds") or {}
    enabled_metrics = set(configuration.get("enabled_metrics") or [])
    inactive_titles = []
    for key, label in METRIC_LABELS.items():
        policy = thresholds.get(key) or {}
        if key not in enabled_metrics or not policy.get("enabled", True):
            inactive_titles.append(f"{label} threshold on")

    if not inactive_titles:
        return 0

    alerts = (await db.execute(select(Alert).where(
        Alert.device_id == device_id,
        Alert.root_cause == "METRIC_THRESHOLD",
        Alert.is_resolved.is_(False),
    ))).scalars().all()
    now = datetime.now(timezone.utc)
    resolved = 0
    for alert in alerts:
        if any(alert.title.startswith(title) for title in inactive_titles):
            alert.is_resolved = True
            alert.resolved_at = now
            resolved += 1
    return resolved
