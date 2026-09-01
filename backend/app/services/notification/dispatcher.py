import json
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone

import aiosmtplib
import httpx
import structlog
from sqlalchemy import select

from app.database import async_session_factory
from app.models.platform import NotificationDelivery, NotificationIntegration, NotificationRule
from app.security import decrypt_secret

logger = structlog.get_logger()


def _event_type(title: str, recovery: bool) -> str:
    if recovery: return "RECOVERY"
    upper = title.upper()
    if "REDUND" in upper: return "REDUNDANCY_CRITICAL" if "CRITICAL" in upper or "CRÍTIC" in upper else "REDUNDANCY_DEGRADED"
    if "LINK" in upper or "ENLACE" in upper: return "LINK_DOWN"
    return "DEVICE_DOWN"


async def dispatch_persisted_notifications(title: str, message: str, severity: str, alert_id: int, recovery: bool = False):
    async with async_session_factory() as db:
        event = _event_type(title, recovery)
        rules = (await db.execute(select(NotificationRule).where(NotificationRule.enabled == True))).scalars().all()
        rules = [rule for rule in rules if ((recovery and rule.notify_recovery) or (not recovery and rule.event_type == event and rule.severity == severity))
            and (not rule.source or rule.source.lower() in f"{title} {message}".lower())]
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
        requested = {channel for rule in due_rules for channel in (rule.channels or [])}
        integrations = (await db.execute(select(NotificationIntegration).where(NotificationIntegration.enabled == True))).scalars().all()
        sent = False
        for integration in integrations:
            if integration.provider not in requested: continue
            try: await _send(integration, title, message, severity); sent = True
            except Exception as exc: logger.error("persisted_notification_failed", provider=integration.provider, error=type(exc).__name__)
        if sent:
            for rule in due_rules:
                delivery = deliveries[rule.id]
                if delivery:
                    delivery.last_sent_at = now; delivery.delivery_count += 1; delivery.last_kind = "RECOVERY" if recovery else "ALERT"
                else:
                    db.add(NotificationDelivery(alert_id=alert_id, rule_id=rule.id, last_sent_at=now,
                        delivery_count=1, last_kind="RECOVERY" if recovery else "ALERT"))
            await db.commit()


async def _send(item: NotificationIntegration, title: str, message: str, severity: str):
    cfg = item.public_config or {}; secrets = json.loads(decrypt_secret(item.encrypted_secrets) or "{}")
    text = f"{severity}\n\n{title}\n\n{message}"
    if item.provider == "TELEGRAM":
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"https://api.telegram.org/bot{secrets['bot_token']}/sendMessage", json={"chat_id": cfg["chat_id"], "text": text}); response.raise_for_status()
    elif item.provider == "WHATSAPP":
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(cfg["api_url"], headers={"Authorization": f"Bearer {secrets['api_token']}"}, json={"sender": cfg.get("sender_id"), "recipient": cfg.get("recipient"), "message": text}); response.raise_for_status()
    elif item.provider == "EMAIL":
        mail = EmailMessage(); mail["Subject"] = f"[{severity}] {title}"; mail["From"] = cfg["from_address"]; mail["To"] = ", ".join(cfg["recipients"]); mail.set_content(text)
        await aiosmtplib.send(mail, hostname=cfg["smtp_server"], port=int(cfg.get("smtp_port", 587)), username=cfg.get("username") or None, password=secrets.get("password") or None, start_tls=bool(cfg.get("tls")) and not bool(cfg.get("ssl")), use_tls=bool(cfg.get("ssl")), timeout=10)
    logger.info("persisted_notification_sent", provider=item.provider, title=title)
