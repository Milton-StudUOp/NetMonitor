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
from app.security import decrypt_secret
from app.services.notification.dispatcher import dispatch_persisted_notifications
from app.services.windows_monitoring import WinRMTransport, WindowsMonitoringError, WindowsMonitoringProvider

logger = structlog.get_logger()


def service_state_transition(current: str, healthy: bool, failures: int, successes: int,
                             failure_threshold: int, recovery_threshold: int) -> tuple[str, int, int]:
    if healthy:
        failures = 0; successes += 1
        state = "RECOVERING" if current == "DOWN" and successes < recovery_threshold else (
            "UP" if successes >= recovery_threshold else current)
    else:
        successes = 0; failures += 1
        state = "DOWN" if failures >= failure_threshold else "SUSPECTED"
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
            metric_device_ids = (await db.execute(select(DeviceCapability.device_id).where(
                DeviceCapability.provider == "WINDOWS"))).scalars().all()
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
            capability = (await db.execute(select(DeviceCapability).where(DeviceCapability.device_id == device_id,
                DeviceCapability.provider == "WINDOWS"))).scalar_one_or_none()
            enabled_metrics = (capability.diagnostics or {}).get("enabled_metrics", []) if capability else []
            credential = (await db.execute(select(DeviceMonitoringCredential).where(
                DeviceMonitoringCredential.device_id == device_id, DeviceMonitoringCredential.enabled.is_(True)))).scalar_one_or_none()
            if not credential or (not services and not enabled_metrics): return
            password = decrypt_secret(credential.encrypted_password)
            if not password: return
            provider = WindowsMonitoringProvider(WinRMTransport(device.ip_address, credential.username, password,
                credential.port, credential.use_https, credential.verify_certificate, credential.authentication))
            started = perf_counter()
            try:
                observed = await provider.check_services([x.name for x in services])
                elapsed = round((perf_counter() - started) * 1000, 2)
                for item in services: await self._apply_service_result(db, item, observed.get(item.name, "unknown"), None, elapsed, now)
                last_metric = self._last_metric_check.get(device_id)
                if enabled_metrics and (not last_metric or now - last_metric >= timedelta(seconds=60)):
                    values = await provider.collect_system_metrics()
                    allowed = set(enabled_metrics)
                    details = {key: values.get(key) for key in ("network_interfaces", "network_adapters",
                        "processes", "system_information", "events")}
                    db.add(SystemMetricSnapshot(device_id=device_id,
                        cpu_percent=values.get("cpu_percent") if "cpu" in allowed else None,
                        memory_percent=values.get("memory_percent") if "memory" in allowed else None,
                        uptime_seconds=values.get("uptime_seconds") if "uptime" in allowed else None,
                        storage={"disks": values.get("storage") or [] if "storage" in allowed else [],
                            **{key: value if key in allowed or (key == "network_adapters" and "network_interfaces" in allowed) else []
                               for key, value in details.items()}})); self._last_metric_check[device_id] = now
            except (WindowsMonitoringError, asyncio.TimeoutError) as exc:
                code = exc.code if isinstance(exc, WindowsMonitoringError) else "CHECK_TIMEOUT"
                for item in services:
                    db.add(ServiceCheckHistory(service_id=item.id, observed_state="unknown", monitor_state="UNKNOWN",
                        error_code=code, response_ms=None, checked_at=now))
                    item.last_checked_at = now; item.next_check_at = now + timedelta(seconds=max(300, item.check_interval))
            await db.commit()

    async def _apply_service_result(self, db, item, observed: str, error_code: str | None,
                                    response_ms: float, now: datetime):
        healthy = observed == item.expected_state
        item.monitor_state, item.consecutive_failures, item.consecutive_successes = service_state_transition(
            item.monitor_state, healthy, item.consecutive_failures, item.consecutive_successes,
            item.failure_threshold, item.recovery_threshold)
        item.state = observed; item.last_checked_at = now; item.next_check_at = now + timedelta(seconds=item.check_interval)
        db.add(ServiceCheckHistory(service_id=item.id, observed_state=observed, monitor_state=item.monitor_state,
            error_code=error_code, response_ms=response_ms, checked_at=now))
        title = f"Windows service {item.name} on device #{item.device_id}"
        active = (await db.execute(select(Alert).where(Alert.title == title, Alert.is_resolved.is_(False)))).scalar_one_or_none()
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
