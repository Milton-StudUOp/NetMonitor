import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.device import Device, DeviceStatus
from app.models.link import Link, LinkStatus
from app.models.interface import Interface, InterfaceStatus
from app.models.redundancy_group import RedundancyGroup
from app.models.monitoring_result import MetricAggregate, MonitoringResult, MonitoringTargetType, MonitoringStatus
from app.services.icmp_monitor import ping_target
from app.services.snmp_monitor import query_snmp_interface
from app.services.redundancy_engine import evaluate_redundancy_group
from app.utils.state_machine import state_tracker
from app.models.alert import AlertSeverity
from app.services.alert_engine import trigger_alert, auto_resolve_alerts
from app.api.websocket import manager as ws_manager
from app.models.platform import SystemSetting
from app.models.alert import Alert

logger = structlog.get_logger()


def device_status_alert_severity(status: DeviceStatus) -> AlertSeverity:
    """Return the operational severity for a device status transition.

    A confirmed device outage is always critical.  Device importance must not
    downgrade an actual outage; warning is reserved for degraded operation.
    """
    if status == DeviceStatus.OFFLINE:
        return AlertSeverity.CRITICAL
    if status == DeviceStatus.DEGRADED:
        return AlertSeverity.WARNING
    return AlertSeverity.INFORMATION


class MonitoringEngine:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._maintenance_task: asyncio.Task | None = None
        self._latest_device_probes: dict[int, dict] = {}
        self._cycle_interval = 5
        self._retention_days = 90
        self._aggregate_retention_days = 1825
        self._last_retention_cleanup: datetime | None = None
        self.last_cycle_started_at: datetime | None = None
        self.last_cycle_completed_at: datetime | None = None
        self.last_cycle_duration_seconds: float | None = None
        self.last_cycle_error: str | None = None
        self.completed_cycles = 0
        self.failed_cycles = 0

    async def load_configuration(self):
        async with async_session_factory() as db:
            setting = await db.get(SystemSetting, "general")
            values = setting.value if setting else {}
            self._cycle_interval = max(1, min(int(values.get("default_monitoring_interval", 5)), 60))
            self._retention_days = max(1, int(values.get("retention_days", 90)))
            self._aggregate_retention_days = max(self._retention_days, int(values.get("aggregate_retention_days", 1825)))
            state_tracker.failures_to_down = max(1, int(values.get("failure_threshold", state_tracker.failures_to_down)))
            state_tracker.successes_to_up = max(1, int(values.get("success_threshold", state_tracker.successes_to_up)))
            logger.info("monitoring_configuration_loaded", cycle_interval=self._cycle_interval,
                retention_days=self._retention_days, failures_to_down=state_tracker.failures_to_down,
                successes_to_up=state_tracker.successes_to_up)

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._main_loop())
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
            logger.info("monitoring_engine_started")

    def stop(self):
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
            if self._maintenance_task:
                self._maintenance_task.cancel()
            logger.info("monitoring_engine_stopped")

    async def stop_and_wait(self):
        tasks = [task for task in (self._task, self._maintenance_task) if task]
        self.stop()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._task = None
        self._maintenance_task = None

    async def _main_loop(self):
        while self._running:
            self.last_cycle_started_at = datetime.now(timezone.utc)
            try:
                async with async_session_factory() as db:
                    await self._probe_all_devices(db)
                    await self._probe_all_links(db)
                    await self._evaluate_all_redundancy_groups(db)
                self.last_cycle_completed_at = datetime.now(timezone.utc)
                self.last_cycle_duration_seconds = (self.last_cycle_completed_at - self.last_cycle_started_at).total_seconds()
                self.last_cycle_error = None; self.completed_cycles += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_cycle_error = type(e).__name__; self.failed_cycles += 1
                logger.error("monitoring_engine_loop_error", error_type=type(e).__name__)

            # Run cycle every 5 seconds
            await asyncio.sleep(self._cycle_interval)

    async def _maintenance_loop(self):
        while self._running:
            try:
                async with async_session_factory() as db:
                    await self._cleanup_retention(db)
            except asyncio.CancelledError:
                break
            except Exception as error:
                logger.error("retention_cleanup_failed", error_type=type(error).__name__)
            await asyncio.sleep(3600)

    async def _cleanup_retention(self, db):
        now = datetime.now(timezone.utc)
        if self._last_retention_cleanup and now - self._last_retention_cleanup < timedelta(hours=1): return
        cutoff = now - timedelta(days=self._retention_days)
        await self._aggregate_expiring_records(db, cutoff)
        aggregate_cutoff = now - timedelta(days=self._aggregate_retention_days)
        await db.execute(delete(MetricAggregate).where(MetricAggregate.bucket_start < aggregate_cutoff))
        await db.execute(delete(Alert).where(Alert.is_resolved == True, Alert.resolved_at < cutoff))
        await db.commit(); self._last_retention_cleanup = now

    async def _aggregate_expiring_records(self, db, cutoff):
        batch_size = 5000
        while True:
            records = (await db.execute(
                select(MonitoringResult)
                .where(MonitoringResult.timestamp < cutoff)
                .order_by(MonitoringResult.timestamp, MonitoringResult.id)
                .limit(batch_size)
            )).scalars().all()
            if not records:
                break
            for granularity in ("HOURLY", "DAILY"):
                grouped = {}
                for item in records:
                    timestamp = item.timestamp.replace(tzinfo=timezone.utc) if item.timestamp.tzinfo is None else item.timestamp.astimezone(timezone.utc)
                    bucket = timestamp.replace(minute=0, second=0, microsecond=0)
                    if granularity == "DAILY":
                        bucket = bucket.replace(hour=0)
                    key = (item.target_type.value, item.target_id, bucket)
                    values = grouped.setdefault(key, {"samples": 0, "up": 0, "down": 0, "latencies": [], "losses": []})
                    values["samples"] += 1
                    values["up"] += item.status == MonitoringStatus.UP
                    values["down"] += item.status == MonitoringStatus.DOWN
                    if item.latency_ms is not None:
                        values["latencies"].append(item.latency_ms)
                    if item.packet_loss_pct is not None:
                        values["losses"].append(item.packet_loss_pct)
                for (target_type, target_id, bucket), values in grouped.items():
                    aggregate = (await db.execute(select(MetricAggregate).where(
                        MetricAggregate.target_type == target_type,
                        MetricAggregate.target_id == target_id,
                        MetricAggregate.granularity == granularity,
                        MetricAggregate.bucket_start == bucket,
                    ))).scalar_one_or_none()
                    if aggregate is None:
                        aggregate = MetricAggregate(target_type=target_type, target_id=target_id, granularity=granularity,
                            bucket_start=bucket, sample_count=0, up_count=0, down_count=0,
                            latency_sum=0, latency_count=0, packet_loss_sum=0, packet_loss_count=0)
                        db.add(aggregate)
                    aggregate.sample_count += values["samples"]
                    aggregate.up_count += values["up"]
                    aggregate.down_count += values["down"]
                    aggregate.latency_sum += sum(values["latencies"])
                    aggregate.latency_count += len(values["latencies"])
                    batch_max = max(values["latencies"], default=None)
                    if batch_max is not None:
                        aggregate.latency_max = max(aggregate.latency_max or batch_max, batch_max)
                    aggregate.packet_loss_sum += sum(values["losses"])
                    aggregate.packet_loss_count += len(values["losses"])
            await db.execute(delete(MonitoringResult).where(MonitoringResult.id.in_([item.id for item in records])))
            await db.commit()

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
            dependency_down, dependency_reason = await self._detect_downstream_dependency(
                device,
                gateway_ping_cache,
            )
            initial_state = "UP" if device.status == DeviceStatus.ONLINE else "DOWN" if device.status == DeviceStatus.OFFLINE else "UNKNOWN"
            stable_state, _ = state_tracker.update("DEVICE", device.id, is_up, initial_state)
            new_status = DeviceStatus.ONLINE if stable_state == "UP" else (
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
                        severity=device_status_alert_severity(new_status),
                        title=f"Device unavailable: {device.name}",
                        message=f"The device '{device.name}' (IP: {device.ip_address}) did not respond to ICMP probes.",
                        db=db,
                        device_id=device.id,
                        root_cause="No ICMP response. The device may be powered off, unreachable, or physically disconnected.",
                    )
                elif new_status == DeviceStatus.DEGRADED:
                    await trigger_alert(
                        severity=device_status_alert_severity(new_status),
                        title=f"Device affected by an upstream dependency: {device.name}",
                        message=f"The device '{device.name}' did not respond and its gateway or primary link is likely unavailable.",
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
            return True, f"The associated primary link is down: {device.primary_link.name}."

        if device.gateway_device and device.gateway_device.status in {
            DeviceStatus.OFFLINE,
            DeviceStatus.DEGRADED,
        }:
            return True, f"The associated gateway is {device.gateway_device.status.value}: {device.gateway_device.name}."

        gateway_ip = (device.gateway_ip_address or "").strip()
        if gateway_ip and gateway_ip != (device.ip_address or "").strip():
            if gateway_ip not in gateway_ping_cache:
                gateway_ping_cache[gateway_ip] = await ping_target(gateway_ip, count=1)
            if not gateway_ping_cache[gateway_ip]["is_up"]:
                return True, f"The gateway did not respond to ICMP probes: {gateway_ip}."

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
                    src_name = link.source_device.name if link.source_device else "Source"
                    dst_name = link.destination_device.name if link.destination_device else "Destination"
                    await trigger_alert(
                        severity=AlertSeverity.WARNING,
                        title=f"Communication link down: {link.name}",
                        message=f"The link '{link.name}' between {src_name} and {dst_name} has lost connectivity.",
                        db=db,
                        link_id=link.id,
                        root_cause="The physical channel may be interrupted or an endpoint device may be unavailable.",
                    )
                elif new_status == LinkStatus.DEGRADED:
                    src_name = link.source_device.name if link.source_device else "Source"
                    dst_name = link.destination_device.name if link.destination_device else "Destination"
                    await trigger_alert(
                        severity=AlertSeverity.WARNING,
                        title=f"Link partially available: {link.name}",
                        message=f"Only one endpoint is responding: {src_name} ↔ {dst_name}.",
                        db=db,
                        link_id=link.id,
                        root_cause="One endpoint is reachable while the other is offline or degraded.",
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
