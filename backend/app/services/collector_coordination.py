"""Portable leases used to coordinate multiple NetMonitor collectors.

The primary database is the durable work queue: a collector owns a scope only
until its lease expires.  Therefore another node can take over after a crash
without relying on process-local state, shared disks, or a database-specific
advisory lock.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import async_session_factory
from app.models.platform import CollectorLease


class CollectorCoordinator:
    def __init__(self):
        settings = get_settings()
        self.owner_id = settings.collector_id
        self.lease_seconds = max(10, settings.COLLECTOR_LEASE_SECONDS)

    async def claim(self, scope: str, lease_seconds: int | None = None) -> bool:
        """Acquire or renew a lease using conditional writes.

        A conditional update avoids a read-then-write race for an expired
        lease. A unique primary key resolves the first-claim race safely.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(10, lease_seconds or self.lease_seconds))
        async with async_session_factory() as db:
            renewed = await db.execute(update(CollectorLease).where(
                CollectorLease.scope == scope,
                (CollectorLease.owner_id == self.owner_id) | (CollectorLease.expires_at <= now),
            ).values(owner_id=self.owner_id, expires_at=expires_at))
            if renewed.rowcount:
                await db.commit()
                return True
            try:
                db.add(CollectorLease(scope=scope, owner_id=self.owner_id, expires_at=expires_at))
                await db.commit()
                return True
            except IntegrityError:
                await db.rollback()
                return False

    async def release(self, scope: str) -> None:
        async with async_session_factory() as db:
            await db.execute(delete(CollectorLease).where(
                CollectorLease.scope == scope, CollectorLease.owner_id == self.owner_id,
            ))
            await db.commit()


collector_coordinator = CollectorCoordinator()
