from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert import Alert, AlertSeverity
from app.models.device import Device, DeviceStatus
from app.models.link import Link, LinkPriority, LinkStatus, LinkType
from app.models.redundancy_group import RedundancyGroup, RedundancyStatus, RedundancyType
from app.models.platform import IconAsset
from app.schemas.topology import (
    DashboardSummary,
    TopologyEdge,
    TopologyEdgeData,
    TopologyGraph,
    TopologyNode,
    TopologyNodeData,
)
from app.utils.networking import get_network_warning

router = APIRouter(tags=["Topology & Dashboard"])


@router.get("/api/topology", response_model=TopologyGraph)
async def get_topology(db: AsyncSession = Depends(get_db)):
    devices_result = await db.execute(select(Device))
    devices = devices_result.scalars().all()
    icons = {icon.id: icon for icon in (await db.execute(select(IconAsset))).scalars().all()}

    links_result = await db.execute(
        select(Link).options(
            selectinload(Link.source_interface),
            selectinload(Link.destination_interface),
        )
    )
    links = links_result.scalars().all()
    device_redundancy_groups = (
        await db.execute(
            select(RedundancyGroup).where(
                RedundancyGroup.redundancy_type == RedundancyType.DEVICE
            )
        )
    ).scalars().all()

    nodes = [
        TopologyNode(
            id=f"device_{d.id}",
            type="customDevice",
            data=TopologyNodeData(
                label=d.name,
                ip_address=d.ip_address,
                gateway_ip_address=d.gateway_ip_address,
                gateway_device_id=d.gateway_device_id,
                primary_link_id=d.primary_link_id,
                network=d.network,
                device_type=d.device_type,
                status=d.status,
                location=d.location,
                is_critical=d.is_critical,
                icon_id=d.icon_id,
                icon_key=icons[d.icon_id].key if d.icon_id in icons else None,
                icon_name=icons[d.icon_id].lucide_name if d.icon_id in icons else None,
                icon_custom_data=icons[d.icon_id].custom_data if d.icon_id in icons else None,
                icon_mime_type=icons[d.icon_id].mime_type if d.icon_id in icons else None,
            ),
        )
        for d in devices
    ]

    devices_by_id = {device.id: device for device in devices}
    edges = []
    for l in links:
        source_device = devices_by_id.get(l.source_device_id)
        destination_device = devices_by_id.get(l.destination_device_id)
        network_warning_reason = (
            get_network_warning(source_device, destination_device)
            if source_device and destination_device
            else None
        )
        edges.append(TopologyEdge(
            id=f"link_{l.id}",
            source=f"device_{l.source_device_id}",
            target=f"device_{l.destination_device_id}",
            animated=l.status == LinkStatus.UP,
            label="⚠ Redes distintas — requer roteamento" if network_warning_reason else l.name,
            style={
                "stroke": "#f59e0b" if network_warning_reason else ("#10b981" if l.status == LinkStatus.UP else ("#ef4444" if l.status == LinkStatus.DOWN else "#f59e0b")),
                "strokeWidth": 3 if l.priority.value == "PRIMARY" else 2,
                "strokeDasharray": "5,5" if l.priority.value == "SECONDARY" else None,
            },
            labelStyle={"fill": "#fbbf24" if network_warning_reason else "#cbd5e1", "fontWeight": 600},
            labelBgStyle={"fill": "#0f172a", "fillOpacity": 0.9},
            data=TopologyEdgeData(
                label=l.name,
                status=l.status,
                priority=l.priority,
                link_type=l.link_type,
                source_interface=l.source_interface.interface_name if l.source_interface else None,
                destination_interface=l.destination_interface.interface_name if l.destination_interface else None,
                network_warning=bool(network_warning_reason),
                network_warning_reason=network_warning_reason,
            ),
        ))

    redundancy_link_status = {
        RedundancyStatus.NORMAL: LinkStatus.UP,
        RedundancyStatus.DEGRADED: LinkStatus.DEGRADED,
        RedundancyStatus.CRITICAL: LinkStatus.DOWN,
        RedundancyStatus.UNKNOWN: LinkStatus.UNKNOWN,
    }
    redundancy_colors = {
        RedundancyStatus.NORMAL: "#22d3ee",
        RedundancyStatus.DEGRADED: "#f59e0b",
        RedundancyStatus.CRITICAL: "#ef4444",
        RedundancyStatus.UNKNOWN: "#64748b",
    }
    for group in device_redundancy_groups:
        if group.primary_device_id is None or group.secondary_device_id is None:
            continue
        edges.append(
            TopologyEdge(
                id=f"device_redundancy_{group.id}",
                source=f"device_{group.primary_device_id}",
                target=f"device_{group.secondary_device_id}",
                animated=group.status == RedundancyStatus.NORMAL,
                style={
                    "stroke": redundancy_colors[group.status],
                    "strokeWidth": 3,
                    "strokeDasharray": "8,6",
                },
                data=TopologyEdgeData(
                    label=group.name,
                    status=redundancy_link_status[group.status],
                    priority=LinkPriority.SECONDARY,
                    link_type=LinkType.OTHER,
                    is_redundancy=True,
                    redundancy_status=group.status,
                ),
            )
        )

    return TopologyGraph(nodes=nodes, edges=edges)


@router.get("/api/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
    # Devices counts
    devices = (await db.execute(select(Device))).scalars().all()
    total_devices = len(devices)
    online_devices = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)
    offline_devices = sum(1 for d in devices if d.status == DeviceStatus.OFFLINE)
    degraded_devices = sum(1 for d in devices if d.status == DeviceStatus.DEGRADED)
    unknown_devices = sum(1 for d in devices if d.status == DeviceStatus.UNKNOWN)

    # Links counts
    links = (await db.execute(select(Link))).scalars().all()
    total_links = len(links)
    up_links = sum(1 for l in links if l.status == LinkStatus.UP)
    down_links = sum(1 for l in links if l.status == LinkStatus.DOWN)
    degraded_links = sum(1 for l in links if l.status == LinkStatus.DEGRADED)

    # Redundancy groups
    groups = (await db.execute(select(RedundancyGroup))).scalars().all()
    total_redundancy_groups = len(groups)
    normal_rg = sum(1 for g in groups if g.status == RedundancyStatus.NORMAL)
    degraded_rg = sum(1 for g in groups if g.status == RedundancyStatus.DEGRADED)
    critical_rg = sum(1 for g in groups if g.status == RedundancyStatus.CRITICAL)

    # Active alerts
    active_alerts = (await db.execute(select(Alert).where(Alert.is_resolved == False))).scalars().all()
    active_alerts_count = len(active_alerts)
    critical_alerts_count = sum(1 for a in active_alerts if a.severity == AlertSeverity.CRITICAL)

    return DashboardSummary(
        total_devices=total_devices,
        online_devices=online_devices,
        offline_devices=offline_devices,
        degraded_devices=degraded_devices,
        unknown_devices=unknown_devices,
        total_links=total_links,
        up_links=up_links,
        down_links=down_links,
        degraded_links=degraded_links,
        total_redundancy_groups=total_redundancy_groups,
        normal_redundancy_groups=normal_rg,
        degraded_redundancy_groups=degraded_rg,
        critical_redundancy_groups=critical_rg,
        active_alerts_count=active_alerts_count,
        critical_alerts_count=critical_alerts_count,
    )
