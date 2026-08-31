import asyncio
import structlog
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.device import Device, DeviceStatus
from app.models.link import Link, LinkStatus
from app.models.interface import Interface, InterfaceStatus
from app.models.redundancy_group import RedundancyGroup
from app.models.monitoring_result import MonitoringResult, MonitoringTargetType, MonitoringStatus
from app.services.icmp_monitor import ping_target
from app.services.snmp_monitor import query_snmp_interface
from app.services.redundancy_engine import evaluate_redundancy_group
from app.utils.state_machine import state_tracker
from app.models.alert import AlertSeverity
from app.services.alert_engine import trigger_alert, auto_resolve_alerts
from app.api.websocket import manager as ws_manager

logger = structlog.get_logger()


class MonitoringEngine:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._latest_device_probes: dict[int, dict] = {}

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._main_loop())
            logger.info("monitoring_engine_started")

    def stop(self):
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
            logger.info("monitoring_engine_stopped")

    async def _main_loop(self):
        while self._running:
            try:
                async with async_session_factory() as db:
                    await self._probe_all_devices(db)
                    await self._probe_all_links(db)
                    await self._evaluate_all_redundancy_groups(db)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("monitoring_engine_loop_error", error=str(e))

            # Run cycle every 5 seconds
            await asyncio.sleep(5)

    async def _probe_all_devices(self, db):
        devices = (await db.execute(select(Device).options(
            selectinload(Device.gateway_device),
            selectinload(Device.primary_link),
        ))).scalars().all()
        gateway_ping_cache: dict[str, dict] = {}
        self._latest_device_probes = {}

        for device in devices:
            if not device.ip_address:
                continue

            ping_res = await ping_target(device.ip_address, count=2)
            self._latest_device_probes[device.id] = ping_res
            is_up = ping_res["is_up"]
            logger.info("probe_device", name=device.name, ip=device.ip_address, is_up=is_up, ping_res=ping_res)
            dependency_down, dependency_reason = await self._detect_downstream_dependency(
                device,
                gateway_ping_cache,
            )
            new_status = DeviceStatus.ONLINE if is_up else (
                DeviceStatus.DEGRADED if dependency_down else DeviceStatus.OFFLINE
            )
            if device.status != new_status:
                device.status = new_status
                await db.commit()
                await ws_manager.broadcast("device_status_change", {
                    "id": device.id,
                    "name": device.name,
                    "status": new_status.value,
                })

                # Trigger real alerts on status change
                if new_status == DeviceStatus.OFFLINE:
                    await trigger_alert(
                        severity=AlertSeverity.CRITICAL if device.is_critical else AlertSeverity.WARNING,
                        title=f"Equipamento Inacessível: {device.name}",
                        message=f"O equipamento '{device.name}' (IP: {device.ip_address}) não respondeu aos pings ICMP.",
                        db=db,
                        device_id=device.id,
                        root_cause="Sem resposta ICMP - Equipamento desligado, fora da rede ou com cabo desconectado.",
                    )
                elif new_status == DeviceStatus.DEGRADED:
                    await trigger_alert(
                        severity=AlertSeverity.WARNING,
                        title=f"Equipamento impactado por dependência: {device.name}",
                        message=f"O equipamento '{device.name}' não respondeu, mas há falha provável no gateway ou link principal.",
                        db=db,
                        device_id=device.id,
                        root_cause=dependency_reason,
                    )
                elif new_status == DeviceStatus.ONLINE:
                    await auto_resolve_alerts(db, device_id=device.id)

            # Record time-series result
            res_entry = MonitoringResult(
                target_type=MonitoringTargetType.DEVICE,
                target_id=device.id,
                status=MonitoringStatus.UP if is_up else MonitoringStatus.DOWN,
                latency_ms=ping_res.get("latency_ms"),
                packet_loss_pct=ping_res.get("packet_loss_pct"),
            )
            db.add(res_entry)
        await db.commit()

    async def _detect_downstream_dependency(self, device: Device, gateway_ping_cache: dict[str, dict]) -> tuple[bool, str | None]:
        if device.primary_link and device.primary_link.status == LinkStatus.DOWN:
            return True, f"Link principal associado está DOWN: {device.primary_link.name}."

        if device.gateway_device and device.gateway_device.status in {
            DeviceStatus.OFFLINE,
            DeviceStatus.DEGRADED,
        }:
            return True, f"Gateway associado está {device.gateway_device.status.value}: {device.gateway_device.name}."

        gateway_ip = (device.gateway_ip_address or "").strip()
        if gateway_ip and gateway_ip != (device.ip_address or "").strip():
            if gateway_ip not in gateway_ping_cache:
                gateway_ping_cache[gateway_ip] = await ping_target(gateway_ip, count=1)
            if not gateway_ping_cache[gateway_ip]["is_up"]:
                return True, f"Gateway ICMP sem resposta: {gateway_ip}."

        return False, None

    async def _probe_all_links(self, db):
        links = (await db.execute(select(Link).options(
            selectinload(Link.source_device),
            selectinload(Link.destination_device),
        ))).scalars().all()

        for link in links:
            source_status = link.source_device.status if link.source_device else DeviceStatus.UNKNOWN
            destination_status = link.destination_device.status if link.destination_device else DeviceStatus.UNKNOWN

            # Each endpoint keeps its independently probed status. The link
            # represents the combined availability of its two endpoints.
            if source_status == DeviceStatus.ONLINE and destination_status == DeviceStatus.ONLINE:
                new_status = LinkStatus.UP
            elif source_status == DeviceStatus.OFFLINE and destination_status == DeviceStatus.OFFLINE:
                new_status = LinkStatus.DOWN
            elif DeviceStatus.UNKNOWN in {source_status, destination_status}:
                new_status = LinkStatus.UNKNOWN
            else:
                new_status = LinkStatus.DEGRADED

            ping_res = self._latest_device_probes.get(link.destination_device_id, {})
            is_up = new_status == LinkStatus.UP
            if link.status != new_status:
                link.status = new_status
                await db.commit()
                await ws_manager.broadcast("link_status_change", {
                    "id": link.id,
                    "name": link.name,
                    "status": new_status.value,
                })

                # Trigger real alert on link down
                if new_status == LinkStatus.DOWN:
                    src_name = link.source_device.name if link.source_device else "Origem"
                    dst_name = link.destination_device.name if link.destination_device else "Destino"
                    await trigger_alert(
                        severity=AlertSeverity.WARNING,
                        title=f"Enlace de Comunicação Caído: {link.name}",
                        message=f"O enlace '{link.name}' entre {src_name} e {dst_name} perdeu conectividade.",
                        db=db,
                        link_id=link.id,
                        root_cause="Interrupção no canal físico ou equipamento de ponta inoperante.",
                    )
                elif new_status == LinkStatus.DEGRADED:
                    src_name = link.source_device.name if link.source_device else "Origem"
                    dst_name = link.destination_device.name if link.destination_device else "Destino"
                    await trigger_alert(
                        severity=AlertSeverity.WARNING,
                        title=f"Enlace Parcialmente Disponível: {link.name}",
                        message=f"Apenas uma ponta do enlace responde: {src_name} ↔ {dst_name}.",
                        db=db,
                        link_id=link.id,
                        root_cause="Uma ponta está acessível e a outra está offline ou degradada.",
                    )
                elif new_status == LinkStatus.UP:
                    await auto_resolve_alerts(db, link_id=link.id)

            res_entry = MonitoringResult(
                target_type=MonitoringTargetType.LINK,
                target_id=link.id,
                status=MonitoringStatus.UP if is_up else MonitoringStatus.DOWN,
                latency_ms=ping_res.get("latency_ms"),
                packet_loss_pct=ping_res.get("packet_loss_pct"),
            )
            db.add(res_entry)
        await db.commit()

    async def _evaluate_all_redundancy_groups(self, db):
        groups = (await db.execute(select(RedundancyGroup))).scalars().all()
        for group in groups:
            await evaluate_redundancy_group(group.id, db)


monitoring_engine = MonitoringEngine()
