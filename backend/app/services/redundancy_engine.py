from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.websocket import manager as ws_manager
from app.models.alert import AlertSeverity
from app.models.device import DeviceStatus
from app.models.link import LinkStatus
from app.models.redundancy_group import (
    RedundancyGroup,
    RedundancyStatus,
    RedundancyType,
    ServiceCheckType,
)
from app.services.alert_engine import auto_resolve_alerts, trigger_alert
from app.services.fault_detector import analyze_probable_root_cause
from app.services.http_monitor import check_http_endpoint
from app.services.icmp_monitor import ping_target
from app.services.tcp_monitor import check_tcp_port

logger = structlog.get_logger()


async def evaluate_redundancy_group(group_id: int, db: AsyncSession) -> RedundancyStatus:
    """Evaluate either a pair of links or a pair of redundant devices."""
    query = (
        select(RedundancyGroup)
        .where(RedundancyGroup.id == group_id)
        .options(
            selectinload(RedundancyGroup.primary_link),
            selectinload(RedundancyGroup.secondary_link),
            selectinload(RedundancyGroup.primary_device),
            selectinload(RedundancyGroup.secondary_device),
        )
    )
    group = (await db.execute(query)).scalar_one_or_none()
    if not group:
        return RedundancyStatus.UNKNOWN

    primary_link = group.primary_link
    secondary_link = group.secondary_link
    primary_device = group.primary_device
    secondary_device = group.secondary_device

    if group.redundancy_type == RedundancyType.DEVICE:
        primary_up = primary_device is not None and primary_device.status == DeviceStatus.ONLINE
        secondary_up = secondary_device is not None and secondary_device.status == DeviceStatus.ONLINE
        primary_status = primary_device.status.value if primary_device else "UNKNOWN"
        secondary_status = secondary_device.status.value if secondary_device else "UNKNOWN"
    else:
        primary_up = primary_link is not None and primary_link.status == LinkStatus.UP
        secondary_up = secondary_link is not None and secondary_link.status == LinkStatus.UP
        primary_status = primary_link.status.value if primary_link else "UNKNOWN"
        secondary_status = secondary_link.status.value if secondary_link else "UNKNOWN"

    service_up = True
    if group.service_check_type == ServiceCheckType.ICMP and group.service_check_target:
        service_up = (await ping_target(group.service_check_target))["is_up"]
    elif (
        group.service_check_type == ServiceCheckType.TCP
        and group.service_check_target
        and group.service_check_port
    ):
        service_up = (
            await check_tcp_port(group.service_check_target, group.service_check_port)
        )["is_up"]
    elif (
        group.service_check_type in (ServiceCheckType.HTTP, ServiceCheckType.HTTPS)
        and group.service_check_target
    ):
        service_up = (await check_http_endpoint(group.service_check_target))["is_up"]

    old_status = group.status
    if primary_up and secondary_up and service_up:
        new_status = RedundancyStatus.NORMAL
    elif not primary_up and not secondary_up:
        new_status = RedundancyStatus.CRITICAL
    else:
        new_status = RedundancyStatus.DEGRADED

    group.status = new_status
    group.last_evaluated = datetime.utcnow()
    await db.commit()

    if old_status == new_status:
        return new_status

    logger.info(
        "redundancy_group_status_change",
        old_status=old_status,
        new_status=new_status,
    )
    await ws_manager.broadcast(
        "redundancy_status_change",
        {
            "group_id": group.id,
            "group_name": group.name,
            "redundancy_type": group.redundancy_type.value,
            "status": new_status.value,
            "primary_status": primary_status,
            "secondary_status": secondary_status,
        },
    )

    if new_status == RedundancyStatus.DEGRADED:
        failed_link = None
        failed_device = None
        if group.redundancy_type == RedundancyType.DEVICE:
            failed_device = primary_device if not primary_up else secondary_device
            target_name = failed_device.name if failed_device else "redundant device"
            target_kind = "device"
            root_cause = "The redundant device did not respond to ICMP probes."
        else:
            failed_link = primary_link if not primary_up else secondary_link
            target_name = failed_link.name if failed_link else "redundant link"
            target_kind = "link"
            analysis = await analyze_probable_root_cause(failed_link, db) if failed_link else {}
            root_cause = analysis.get("root_cause")

        await trigger_alert(
            severity=AlertSeverity.WARNING,
            title=f"Redundancy lost: {group.name}",
            message=(
                f"The {target_kind} '{target_name}' is unavailable. "
                "The remaining unit is maintaining service, but the group no longer has fault tolerance."
            ),
            db=db,
            redundancy_group_id=group.id,
            link_id=failed_link.id if failed_link else None,
            device_id=failed_device.id if failed_device else None,
            root_cause=root_cause,
        )
    elif new_status == RedundancyStatus.CRITICAL:
        await trigger_alert(
            severity=AlertSeverity.CRITICAL,
            title=f"Total service outage: {group.name}",
            message=(
                f"Both the primary and secondary units in '{group.name}' "
                "are unavailable."
            ),
            db=db,
            redundancy_group_id=group.id,
        )
    elif new_status == RedundancyStatus.NORMAL:
        await auto_resolve_alerts(db, redundancy_group_id=group.id)

    return new_status
