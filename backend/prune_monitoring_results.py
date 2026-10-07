"""Prune raw monitoring samples older than the configured retention window.

Run from ``backend``. It is deliberately dry-run by default. ``--apply``
commits small transactions so MySQL is not held by one large delete.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.database import async_session_factory
from app.models.monitoring_result import MonitoringResult
from app.models.platform import SystemSetting


async def prune(apply: bool, batch_size: int) -> None:
    settings = get_settings()
    retention_days = max(1, settings.RAW_METRIC_RETENTION_DAYS)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with async_session_factory() as db:
        eligible = (await db.execute(
            select(func.count()).select_from(MonitoringResult).where(MonitoringResult.timestamp < cutoff)
        )).scalar_one()
        print(f"raw_retention_days={retention_days} eligible_rows={eligible}")
        if not apply:
            return
        general = await db.get(SystemSetting, "general")
        if general:
            general.value = {**(general.value or {}), "retention_days": retention_days}
        else:
            db.add(SystemSetting(key="general", value={"retention_days": retention_days}))
        await db.commit()

    deleted = 0
    batches = 0
    while True:
        removed = None
        for attempt in range(5):
            try:
                async with async_session_factory() as db:
                    identifiers = (await db.execute(
                        select(MonitoringResult.id)
                        .where(MonitoringResult.timestamp < cutoff)
                        .order_by(MonitoringResult.id)
                        .limit(batch_size)
                    )).scalars().all()
                    if not identifiers:
                        removed = 0
                        break
                    await db.execute(delete(MonitoringResult).where(MonitoringResult.id.in_(identifiers)))
                    await db.commit()
                    removed = len(identifiers)
                    break
            except OperationalError as exc:
                arguments = getattr(getattr(exc, "orig", None), "args", ())
                code = arguments[0] if arguments else None
                if code not in {1205, 1213} or attempt == 4:
                    raise
                delay = attempt + 1
                print(f"lock_conflict_retry_seconds={delay}", flush=True)
                await asyncio.sleep(delay)
        if not removed:
            break
        deleted += removed
        batches += 1
        if batches % 100 == 0:
            print(f"deleted_rows={deleted}", flush=True)
    print(f"completed_deleted_rows={deleted}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune raw NetMonitor samples older than the retention window.")
    parser.add_argument("--apply", action="store_true", help="Commit deletions; omit for a count-only dry run.")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    if args.batch_size < 100 or args.batch_size > 50000:
        parser.error("--batch-size must be between 100 and 50000")
    asyncio.run(prune(args.apply, args.batch_size))


if __name__ == "__main__":
    main()
