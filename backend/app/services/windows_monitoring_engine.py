import asyncio
from datetime import datetime, timedelta, timezone
from time import perf_counter

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import OperationalError

from app.database import async_session_factory
from app.models.alert import Alert, AlertSeverity
from app.models.device import Device, DeviceStatus
from app.models.monitoring_provider import (DeviceCapability, DeviceMonitoringCredential, DiscoveredService,
    ServiceCheckHistory, SystemMetricSnapshot)
from app.services.monitoring_providers import MonitoringProviderError
from app.services.provider_factory import provider_for_device
from app.services.metric_alerts import evaluate_metric_alerts
from app.services.interface_metrics import enrich_interface_rates, selected_interfaces
from app.services.notification.dispatcher import dispatch_persisted_notifications
from app.services.collector_coordination import collector_coordinator
from app.config import get_settings

logger = structlog.get_logger()


def service_state_transition(current: str, healthy: bool, failures: int, successes: int,
                             failure_threshold: int, recovery_threshold: int) -> tuple[str, int, int]:
    if healthy:
        failures = 0; successes += 1
        state = "RECOVERING" if current == "DOWN" and successes < recovery_threshold else (
            "UP" if successes >= recovery_threshold else current)
    else:
        successes = 0; failures += 1
        state = "DOWN"
    return state, failures, successes


class WindowsMonitoringEngine:
    def __init__(self, worker_limit: int | None = None):
        self.worker_limit = worker_limit or max(1, get_settings().REMOTE_MONITORING_CONCURRENCY)
        self._running = False; self._task = None; self._semaphore = asyncio.Semaphore(self.worker_limit)

    def start(self):
        if not self._running:
            self._running = True; self._task = asyncio.create_task(self._loop())

    async def stop_and_wait(self):
        self._running = False
        if self._task:
            self._task.cancel(); await asyncio.gather(self._task, return_exceptions=True); self._task = None

    async def _loop(self):
        while self._running:
            try:
                await self.run_due_checks()
            except OperationalError:
                # A collector can race with schema/startup work or encounter a
                # recycled MySQL connection. Retry once without stopping or
                # delaying the independent SSH, SNMP, and WinRM schedules.
                await asyncio.sleep(1)
                try:
                    await self.run_due_checks()
                except Exception as retry_exc:
                    original = getattr(retry_exc, "orig", None)
                    args = getattr(original, "args", ())
                    logger.warning("remote_monitoring_database_retry_failed",
                        database_code=args[0] if args else None,
                        error_type=type(retry_exc).__name__)
            except Exception as exc:
                logger.warning("remote_monitoring_cycle_failed", error_type=type(exc).__name__)
            await asyncio.sleep(10)

    async def run_due_checks(self):
        now = datetime.now(timezone.utc)
        metric_due_before = now - timedelta(seconds=60)
        async with async_session_factory() as db:
            service_device_ids = (await db.execute(select(DiscoveredService.device_id).where(
                DiscoveredService.monitored.is_(True), or_(DiscoveredService.next_check_at.is_(None),
                DiscoveredService.next_check_at <= now)).distinct())).scalars().all()
            active_metric_capabilities = (await db.execute(select(DeviceCapability).join(
                DeviceMonitoringCredential,
                and_(DeviceMonitoringCredential.device_id == DeviceCapability.device_id,
                     DeviceMonitoringCredential.provider == DeviceCapability.provider,
                     DeviceMonitoringCredential.enabled.is_(True)),
            ))).scalars().all()
            metric_device_ids = [item.device_id for item in active_metric_capabilities
                                 if (item.diagnostics or {}).get("enabled_metrics") and self._metric_is_due(item, metric_due_before)]
        device_ids = set(service_device_ids)
        device_ids.update(metric_device_ids)
        claimed_ids = await self._claim_due_checks(device_ids)
        results = await asyncio.gather(
            *(self._check_device(device_id, now, claimed=True) for device_id in claimed_ids),
            return_exceptions=True,
        )
        for device_id, result in zip(claimed_ids, results):
            if isinstance(result, Exception):
                logger.warning("remote_monitoring_device_failed", device_id=device_id,
                    error_type=type(result).__name__)

    async def _claim_due_checks(self, device_ids: set[int]) -> list[int]:
        """Claim remote checks before creating local tasks.

        Iterating beyond an unavailable lease lets a second collector claim the
        next devices in the sorted work set instead of repeatedly contending
        for the same first batch.
        """
        claim_limit = max(0, get_settings().REMOTE_MONITORING_BATCH_SIZE)
        claimed: list[int] = []
        for device_id in sorted(device_ids):
            if claim_limit and len(claimed) >= claim_limit:
                break
            if await collector_coordinator.claim(f"remote-check:{device_id}"):
                claimed.append(device_id)
        return claimed

    @staticmethod
    def _metric_is_due(capability: DeviceCapability, due_before: datetime) -> bool:
        last_collected = capability.last_metric_collected_at
        if last_collected is None:
            return True
        if last_collected.tzinfo is None:
            last_collected = last_collected.replace(tzinfo=timezone.utc)
        return last_collected <= due_before

    async def _check_device(self, device_id: int, now: datetime, claimed: bool = False):
        # Build the transport while a short-lived database session is open,
        # then release that session before SSH, SNMP, or WinRM performs any
        # network I/O. A slow remote host must consume a collector slot, not a
        # database connection from the API pool.
        async with self._semaphore:
            scope = f"remote-check:{device_id}"
            if not claimed and not await collector_coordinator.claim(scope):
                return
            try:
                context = await self._load_check_context(device_id, now)
                if context is None:
                    return
                (device, services, diagnostics, capability_provider, provider, provider_name, enabled_metrics,
                 metric_due, previous_storage, previous_collected_at) = context
                started = perf_counter()
                try:
                    observed = await provider.check_services([item.name for item in services])
                    elapsed = round((perf_counter() - started) * 1000, 2)
                    values = await provider.collect_system_metrics() if metric_due else None
                except (MonitoringProviderError, asyncio.TimeoutError) as exc:
                    code = exc.code if isinstance(exc, MonitoringProviderError) else "CHECK_TIMEOUT"
                    await self._persist_remote_error(services, code, now)
                    return
                await self._persist_check_result(
                    device.id, services, diagnostics or {}, capability_provider, provider_name,
                    enabled_metrics, observed, elapsed, values, previous_storage,
                    previous_collected_at, now,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("remote_monitoring_device_failed", device_id=device_id,
                    error_type=type(exc).__name__)
            finally:
                await collector_coordinator.release(scope)

    async def _load_check_context(self, device_id: int, now: datetime):
        async with async_session_factory() as db:
            device = await db.get(Device, device_id)
            if not device or device.status != DeviceStatus.ONLINE:
                return None
            services = (await db.execute(select(DiscoveredService).where(DiscoveredService.device_id == device_id,
                DiscoveredService.monitored.is_(True), or_(DiscoveredService.next_check_at.is_(None),
                DiscoveredService.next_check_at <= now)))).scalars().all()
            capabilities = (await db.execute(select(DeviceCapability).join(
                DeviceMonitoringCredential,
                and_(DeviceMonitoringCredential.device_id == DeviceCapability.device_id,
                     DeviceMonitoringCredential.provider == DeviceCapability.provider,
                     DeviceMonitoringCredential.enabled.is_(True)),
            ).where(DeviceCapability.device_id == device_id).order_by(
                DeviceCapability.discovered_at.desc(), DeviceCapability.id.desc()))).scalars().all()
            capability = next((item for item in capabilities if (item.diagnostics or {}).get("enabled_metrics")), None)
            enabled_metrics = (capability.diagnostics or {}).get("enabled_metrics", []) if capability else []
            if not services and not enabled_metrics:
                return None
            try:
                provider, provider_name = await provider_for_device(db, device, capability.provider if capability else None)
            except MonitoringProviderError:
                return None
            services = [item for item in services if item.monitoring_provider == provider_name.lower()]
            last_metric = capability.last_metric_collected_at if capability else None
            if last_metric and last_metric.tzinfo is None:
                last_metric = last_metric.replace(tzinfo=timezone.utc)
            metric_due = bool(enabled_metrics) and (not last_metric or now - last_metric >= timedelta(seconds=60))
            previous_storage = None
            previous_collected_at = None
            if metric_due:
                previous = (await db.execute(select(SystemMetricSnapshot).where(
                    SystemMetricSnapshot.device_id == device_id).order_by(
                    SystemMetricSnapshot.collected_at.desc()).limit(1))).scalar_one_or_none()
                previous_storage = previous.storage if previous else None
                previous_collected_at = previous.collected_at if previous else None
            return (device, services, capability.diagnostics if capability else {}, capability.provider if capability else None,
                    provider, provider_name, enabled_metrics,
                    metric_due, previous_storage, previous_collected_at)

    async def _persist_remote_error(self, services, code: str, now: datetime):
        if not services:
            return
        service_ids = [item.id for item in services]
        async with async_session_factory() as db:
            current = (await db.execute(select(DiscoveredService).where(
                DiscoveredService.id.in_(service_ids)))).scalars().all()
            for item in current:
                db.add(ServiceCheckHistory(service_id=item.id, observed_state="unknown", monitor_state="UNKNOWN",
                    error_code=code, response_ms=None, checked_at=now))
                item.last_checked_at = now
                item.next_check_at = now + timedelta(seconds=max(300, item.check_interval))
            await db.commit()

    async def _persist_check_result(self, device_id, services, diagnostics, capability_provider, provider_name, enabled_metrics,
                                    observed, elapsed, values, previous_storage, previous_collected_at, now):
        service_ids = [item.id for item in services]
        async with async_session_factory() as db:
            device = await db.get(Device, device_id)
            if not device:
                return
            current_services = (await db.execute(select(DiscoveredService).where(
                DiscoveredService.id.in_(service_ids)))).scalars().all() if service_ids else []
            for item in current_services:
                await self._apply_service_result(
                    db, item, observed.get(item.name, "unknown"), None, elapsed, now, device.name)
            if values is not None:
                allowed = set(enabled_metrics)
                raw_interfaces = selected_interfaces(values.get("network_interfaces"),
                    diagnostics.get("selected_interface_indexes"))
                values["network_interfaces"] = enrich_interface_rates(raw_interfaces,
                    ((previous_storage or {}).get("network_interfaces") or []), now, previous_collected_at)
                values["network_adapters"] = values["network_interfaces"]
                details = {key: values.get(key) for key in ("network_interfaces", "network_adapters",
                    "processes", "system_information", "events")}
                db.add(SystemMetricSnapshot(device_id=device_id,
                    cpu_percent=values.get("cpu_percent") if "cpu" in allowed else None,
                    memory_percent=values.get("memory_percent") if "memory" in allowed else None,
                    uptime_seconds=values.get("uptime_seconds") if "uptime" in allowed else None,
                    storage={"disks": values.get("storage") or [] if "storage" in allowed else [],
                        **{key: value if key in allowed or (key == "network_adapters" and "network_interfaces" in allowed) else []
                           for key, value in details.items()}}))
                await evaluate_metric_alerts(db, device, values, diagnostics)
                if capability_provider:
                    capability = (await db.execute(select(DeviceCapability).where(
                        DeviceCapability.device_id == device_id,
                        DeviceCapability.provider == capability_provider,
                    ))).scalar_one_or_none()
                    if capability:
                        capability.last_metric_collected_at = now
            await db.commit()

    async def _apply_service_result(self, db, item, observed: str, error_code: str | None,
                                    response_ms: float, now: datetime, device_name: str):
        healthy = observed == item.expected_state
        item.monitor_state, item.consecutive_failures, item.consecutive_successes = service_state_transition(
            item.monitor_state, healthy, item.consecutive_failures, item.consecutive_successes,
            item.failure_threshold, item.recovery_threshold)
        item.state = observed; item.last_checked_at = now; item.next_check_at = now + timedelta(seconds=item.check_interval)
        db.add(ServiceCheckHistory(service_id=item.id, observed_state=observed, monitor_state=item.monitor_state,
            error_code=error_code, response_ms=response_ms, checked_at=now))
        platform = "Linux" if item.monitoring_provider.lower() == "linux" else "Windows"
        title = f"{platform} service {item.name} on {device_name}"
        legacy_title = f"Windows service {item.name} on device #{item.device_id}"
        active = (await db.execute(select(Alert).where(
            Alert.title.in_((title, legacy_title)), Alert.is_resolved.is_(False)))).scalar_one_or_none()
        if active and active.title != title:
            active.title = title
        if item.monitor_state == "DOWN" and not active:
            active = Alert(severity=AlertSeverity(item.severity), title=title,
                message=f"Service {item.display_name} is {observed}; expected {item.expected_state}.",
                device_id=item.device_id, root_cause="SERVICE_DOWN")
            db.add(active); await db.flush()
            if item.notifications_enabled:
                asyncio.create_task(dispatch_persisted_notifications(active.title, active.message, item.severity, active.id))
        elif item.monitor_state == "UP" and active:
            active.is_resolved = True; active.resolved_at = now


windows_monitoring_engine = WindowsMonitoringEngine()
