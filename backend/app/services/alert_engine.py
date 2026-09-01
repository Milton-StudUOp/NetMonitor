import asyncio
import structlog
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertSeverity
from app.api.websocket import manager as ws_manager
from app.services.notification.email import send_email_alert
from app.services.notification.teams import send_teams_alert
from app.services.notification.telegram import send_telegram_alert
from app.services.notification.dispatcher import dispatch_persisted_notifications

logger = structlog.get_logger()


async def trigger_alert(
    severity: AlertSeverity,
    title: str,
    message: str,
    db: AsyncSession,
    device_id: Optional[int] = None,
    link_id: Optional[int] = None,
    redundancy_group_id: Optional[int] = None,
    root_cause: Optional[str] = None,
) -> Alert:
    """
    Creates a new alert if an unresolved one with the same scope doesn't exist already.
    Broadcasts via WebSocket and dispatches to configured notification channels.
    """
    # Check for active unresolved alert on same target
    query = select(Alert).where(Alert.is_resolved == False)
    if device_id:
        query = query.where(Alert.device_id == device_id)
    if link_id:
        query = query.where(Alert.link_id == link_id)
    if redundancy_group_id:
        query = query.where(Alert.redundancy_group_id == redundancy_group_id)

    existing = (await db.execute(query)).scalar_one_or_none()
    if existing:
        # Update message / root cause if changed
        existing.message = message
        if root_cause:
            existing.root_cause = root_cause
        await db.commit()
        asyncio.create_task(dispatch_persisted_notifications(title, message, severity.value, existing.id))
        return existing

    alert = Alert(
        severity=severity,
        title=title,
        message=message,
        device_id=device_id,
        link_id=link_id,
        redundancy_group_id=redundancy_group_id,
        root_cause=root_cause,
        is_resolved=False,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    logger.info("alert_created", id=alert.id, severity=severity, title=title)

    # Broadcast via WebSocket
    await ws_manager.broadcast("new_alert", {
        "id": alert.id,
        "severity": alert.severity.value,
        "title": alert.title,
        "message": alert.message,
        "root_cause": alert.root_cause,
        "created_at": alert.created_at.isoformat(),
    })

    # Async notification dispatch
    asyncio.create_task(_dispatch_notifications(title, message, severity.value, alert.id))
    return alert


async def auto_resolve_alerts(
    db: AsyncSession,
    device_id: Optional[int] = None,
    link_id: Optional[int] = None,
    redundancy_group_id: Optional[int] = None,
    resolution_message: str = "Recuperado automaticamente",
) -> List[Alert]:
    """Auto-resolves unresolved alerts when the target returns to NORMAL/UP state."""
    query = select(Alert).where(Alert.is_resolved == False)
    if device_id:
        query = query.where(Alert.device_id == device_id)
    if link_id:
        query = query.where(Alert.link_id == link_id)
    if redundancy_group_id:
        query = query.where(Alert.redundancy_group_id == redundancy_group_id)

    alerts = (await db.execute(query)).scalars().all()
    resolved = []
    for alert in alerts:
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        resolved.append(alert)

        await ws_manager.broadcast("alert_resolved", {
            "id": alert.id,
            "title": alert.title,
            "resolved_at": alert.resolved_at.isoformat(),
        })

    if resolved:
        await db.commit()
        logger.info("alerts_auto_resolved", count=len(resolved))
        for alert in resolved:
            downtime = alert.resolved_at - alert.created_at.replace(tzinfo=None) if alert.created_at and alert.created_at.tzinfo else alert.resolved_at - alert.created_at
            asyncio.create_task(dispatch_persisted_notifications(
                f"RECOVERY: {alert.title}",
                f"{resolution_message}. Downtime: {max(0, int(downtime.total_seconds() // 60))} minute(s).",
                "INFO",
                alert.id,
                recovery=True,
            ))

    return resolved


async def _dispatch_notifications(title: str, message: str, severity: str, alert_id: int):
    channels = []
    if await send_email_alert(title, message, severity):
        channels.append("email")
    if await send_teams_alert(title, message, severity):
        channels.append("teams")
    if await send_telegram_alert(title, message, severity):
        channels.append("telegram")
    await dispatch_persisted_notifications(title, message, severity, alert_id)
