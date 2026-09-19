import asyncio
from datetime import datetime, timedelta, timezone
from time import perf_counter

import structlog
from sqlalchemy import or_, select

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
    def __init__(self, worker_limit: int = 10):
        self._running = False; self._task = None; self._semaphore = asyncio.Semaphore(worker_limit)
        self._last_metric_check: dict[int, datetime] = {}

    def start(self):
        if not self._running:
            self._running = True; self._task = asyncio.create_task(self._loop())

    async def stop_and_wait(self):
        self._running = False
        if self._task:
            self._task.cancel(); await asyncio.gather(self._task, return_exceptions=True); self._task = None

    async def _loop(self):
        while self._running:
            try: await self.run_due_checks()
            except Exception as exc: logger.warning("windows_monitoring_cycle_failed", error=type(exc).__name__)
            await asyncio.sleep(10)

    async def run_due_checks(self):
        now = datetime.now(timezone.utc)
        async with async_session_factory() as db:
            service_device_ids = (await db.execute(select(DiscoveredService.device_id).where(
                DiscoveredService.monitored.is_(True), or_(DiscoveredService.next_check_at.is_(None),
                DiscoveredService.next_check_at <= now)).distinct())).scalars().all()
            metric_device_ids = (await db.execute(select(DeviceCapability.device_id))).scalars().all()
        device_ids = set(service_device_ids)
        device_ids.update(metric_device_ids)
        await asyncio.gather(*(self._check_device(device_id, now) for device_id in device_ids))

    async def _check_device(self, device_id: int, now: datetime):
        async with self._semaphore, async_session_factory() as db:
            device = await db.get(Device, device_id)
            if not device or device.status != DeviceStatus.ONLINE: return
            services = (await db.execute(select(DiscoveredService).where(DiscoveredService.device_id == device_id,
                DiscoveredService.monitored.is_(True), or_(DiscoveredService.next_check_at.is_(None),
                DiscoveredService.next_check_at <= now)))).scalars().all()
            capabilities = (await db.execute(select(DeviceCapability).where(
                DeviceCapability.device_id == device_id))).scalars().all()
            capability = next((item for item in capabilities if (item.diagnostics or {}).get("enabled_metrics")), None)
            enabled_metrics = (capability.diagnostics or {}).get("enabled_metrics", []) if capability else []
            if not services and not enabled_metrics: return
            try: provider, provider_name = await provider_for_device(db, device, capability.provider if capability else None)
            except MonitoringProviderError: return
            services = [item for item in services if item.monitoring_provider == provider_name.lower()]
            started = perf_counter()
            try:
                observed = await provider.check_services([x.name for x in services])
                elapsed = round((perf_counter() - started) * 1000, 2)
                for item in services: await self._apply_service_result(
                    db, item, observed.get(item.name, "unknown"), None, elapsed, now, device.name)
                last_metric = self._last_metric_check.get(device_id)
                if enabled_metrics and (not last_metric or now - last_metric >= timedelta(seconds=60)):
                    values = await provider.collect_system_metrics()
                    allowed = set(enabled_metrics)
                    previous = (await db.execute(select(SystemMetricSnapshot).where(
                        SystemMetricSnapshot.device_id == device_id).order_by(
                        SystemMetricSnapshot.collected_at.desc()).limit(1))).scalar_one_or_none()
                    raw_interfaces = selected_interfaces(values.get("network_interfaces"),
                        (capability.diagnostics or {}).get("selected_interface_indexes"))
                    values["network_interfaces"] = enrich_interface_rates(raw_interfaces,
                        ((previous.storage or {}).get("network_interfaces") if previous else []), now,
                        previous.collected_at if previous else None)
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
                    await evaluate_metric_alerts(db,device,values,capability.diagnostics or {})
                    self._last_metric_check[device_id] = now
            except (MonitoringProviderError, asyncio.TimeoutError) as exc:
                code = exc.code if isinstance(exc, MonitoringProviderError) else "CHECK_TIMEOUT"
                for item in services:
                    db.add(ServiceCheckHistory(service_id=item.id, observed_state="unknown", monitor_state="UNKNOWN",
                        error_code=code, response_ms=None, checked_at=now))
                    item.last_checked_at = now; item.next_check_at = now + timedelta(seconds=max(300, item.check_interval))
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
