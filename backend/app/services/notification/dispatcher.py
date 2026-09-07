from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from app.database import async_session_factory
from app.models.alert import Alert
from app.models.device import Device
from app.models.link import Link
from app.models.platform import NotificationDelivery, NotificationIntegration, NotificationRule
from app.models.redundancy_group import RedundancyGroup
from app.services.notification.channels import environment_email_integration, send_notification

logger = structlog.get_logger()
SEVERITY_RANK = {"INFORMATION": 0, "WARNING": 1, "CRITICAL": 2}


def _event_type(title: str, recovery: bool) -> str:
    upper = title.upper()
    if "REDUND" in upper:
        base = "REDUNDANCY_CRITICAL" if "CRITICAL" in upper or "CRÍTIC" in upper else "REDUNDANCY_DEGRADED"
    elif "LINK" in upper or "ENLACE" in upper:
        base = "LINK_DOWN"
    else:
        base = "DEVICE_DOWN"
    if not recovery:
        return base
    return {"DEVICE_DOWN": "DEVICE_UP", "LINK_DOWN": "LINK_UP"}.get(base, "RECOVERY")


def _rule_matches(rule, event: str, original_event: str, severity: str, recovery: bool, searchable_text: str) -> bool:
    if rule.source and rule.source.lower() not in searchable_text.lower():
        return False
    severity_matches = SEVERITY_RANK.get(severity, -1) >= SEVERITY_RANK.get(rule.severity, 99)
    if not recovery:
        return rule.event_type == event and severity_matches
    if not rule.notify_recovery:
        return False
    if rule.event_type in {event, "RECOVERY"}:
        return True
    return rule.event_type == original_event and severity_matches


async def dispatch_persisted_notifications(title: str, message: str, severity: str, alert_id: int, recovery: bool = False):
    async with async_session_factory() as db:
        event = _event_type(title, recovery)
        original_event = _event_type(title, False)
        context = await _notification_context(db, alert_id, event, recovery)
        rules = (await db.execute(select(NotificationRule).where(NotificationRule.enabled == True))).scalars().all()
        rules = [rule for rule in rules if _rule_matches(
            rule, event, original_event, severity, recovery, f"{title} {message}"
        )]
        if not rules: return
        now = datetime.now(timezone.utc)
        due_rules = []
        deliveries = {}
        for rule in rules:
            delivery = (await db.execute(select(NotificationDelivery).where(
                NotificationDelivery.alert_id == alert_id, NotificationDelivery.rule_id == rule.id))).scalar_one_or_none()
            deliveries[rule.id] = delivery
            last_sent = delivery.last_sent_at.replace(tzinfo=timezone.utc) if delivery and delivery.last_sent_at.tzinfo is None else (delivery.last_sent_at if delivery else None)
            if recovery or delivery is None or (rule.reminder_minutes > 0 and now - last_sent >= timedelta(minutes=rule.reminder_minutes)):
                due_rules.append(rule)
        if not due_rules: return
        integrations = (await db.execute(select(NotificationIntegration).where(NotificationIntegration.enabled == True))).scalars().all()
        integrations_by_provider = {integration.provider: integration for integration in integrations}
        if "EMAIL" not in integrations_by_provider:
            environment_email = environment_email_integration()
            if environment_email:
                integrations_by_provider["EMAIL"] = environment_email
        delivered_rules = []
        for rule in due_rules:
            rule_sent = False
            for channel in rule.channels or []:
                integration = integrations_by_provider.get(channel)
                if not integration:
                    continue
                try:
                    delivery_severity = "INFORMATION" if recovery else severity
                    await send_notification(integration, title, message, delivery_severity, rule.recipients or [], context)
                    rule_sent = True
                except Exception as exc:
                    logger.error("persisted_notification_failed", provider=channel, rule_id=rule.id, error=type(exc).__name__)
            if rule_sent:
                delivered_rules.append(rule)
        if delivered_rules:
            for rule in delivered_rules:
                delivery = deliveries[rule.id]
                if delivery:
                    delivery.last_sent_at = now; delivery.delivery_count += 1; delivery.last_kind = "RECOVERY" if recovery else "ALERT"
                else:
                    db.add(NotificationDelivery(alert_id=alert_id, rule_id=rule.id, last_sent_at=now,
                        delivery_count=1, last_kind="RECOVERY" if recovery else "ALERT"))
            await db.commit()


async def _notification_context(db, alert_id: int, event_type: str, recovery: bool) -> dict:
    alert = await db.get(Alert, alert_id)
    context = {"alert_id": alert_id, "event_type": event_type, "recovery": recovery}
    if not alert:
        return context
    context["root_cause"] = alert.root_cause
    timestamp = alert.resolved_at if recovery and alert.resolved_at else alert.created_at
    if timestamp:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        context["occurred_at"] = timestamp.astimezone(timezone.utc).isoformat(timespec="seconds")
    if alert.device_id:
        device = await db.get(Device, alert.device_id)
        if device:
            context["target"] = f"{device.name} ({device.ip_address or 'no IP address'})"
    elif alert.link_id:
        link = await db.get(Link, alert.link_id)
        if link:
            context["target"] = link.name
    elif alert.redundancy_group_id:
        group = await db.get(RedundancyGroup, alert.redundancy_group_id)
        if group:
            context["target"] = group.name
    return context
