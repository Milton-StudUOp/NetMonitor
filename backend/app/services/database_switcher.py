from datetime import datetime, timezone
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.database import Base
import app.database as database
from app.db_bootstrap import save_active_database
from app.models.platform import DatabaseConnection
from app.services.database_adapters import (after_table_insert, before_table_insert,
    build_database_url, synchronize_generated_keys)

MIGRATION_BATCH_SIZE = 1000
DEFERRED_FOREIGN_KEYS = {
    ("devices", "gateway_device_id"),
    ("devices", "primary_link_id"),
}


def ordered_migration_tables() -> list:
    """Return a stable FK-aware order, excluding explicitly deferred cycles."""
    tables = dict(Base.metadata.tables)
    dependencies = {
        name: {
            foreign_key.column.table.name
            for foreign_key in table.foreign_keys
            if (name, foreign_key.parent.name) not in DEFERRED_FOREIGN_KEYS
        }
        for name, table in tables.items()
    }
    ordered = []
    remaining = set(tables)
    while remaining:
        ready = sorted(name for name in remaining if not (dependencies[name] & remaining))
        if not ready:
            cycle = ", ".join(sorted(remaining))
            raise RuntimeError(f"Unresolved database dependency cycle: {cycle}")
        ordered.extend(tables[name] for name in ready)
        remaining.difference_update(ready)
    return ordered


async def _copy_table_in_batches(source, destination, item, table, deferred_device_references) -> None:
    ordering = list(table.primary_key.columns)
    statement = select(table).order_by(*ordering) if ordering else select(table)
    async with source.stream(statement) as result:
        async for partition in result.partitions(MIGRATION_BATCH_SIZE):
            rows = [dict(row._mapping) for row in partition]
            if table.name == "devices":
                deferred_device_references.extend({
                    "id": row["id"],
                    "gateway_device_id": row.get("gateway_device_id"),
                    "primary_link_id": row.get("primary_link_id"),
                } for row in rows)
                rows = [{**row, "gateway_device_id": None, "primary_link_id": None} for row in rows]
            if not rows:
                continue
            await before_table_insert(destination, item.database_type, table)
            try:
                await destination.execute(insert(table), rows)
            finally:
                await after_table_insert(destination, item.database_type, table)


async def migrate_and_activate(source_engine: AsyncEngine, item: DatabaseConnection) -> dict:
    target_url = build_database_url(item)
    target = database._create_engine(target_url)
    try:
        async with target.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        tables_by_name = Base.metadata.tables
        tables = ordered_migration_tables()

        async with target.connect() as connection:
            populated = []
            for table in tables:
                count = int((await connection.execute(select(func.count()).select_from(table))).scalar_one())
                if count: populated.append(table.name)
        if populated:
            raise ValueError("Target database is not empty: " + ", ".join(populated[:8]))

        source = await source_engine.connect()
        isolation = "SERIALIZABLE" if source.dialect.name in {"sqlite", "oracle"} else "REPEATABLE READ"
        source = await source.execution_options(isolation_level=isolation)
        try:
            async with source.begin(), target.begin() as destination:
                source_counts = {
                    table.name: int((await source.execute(select(func.count()).select_from(table))).scalar_one())
                    for table in tables
                }
                deferred_device_references = []
                for table in tables:
                    await _copy_table_in_batches(source, destination, item, table, deferred_device_references)
                devices = tables_by_name.get("devices")
                if devices is not None:
                    for references in deferred_device_references:
                        if references["gateway_device_id"] is not None or references["primary_link_id"] is not None:
                            await destination.execute(update(devices).where(devices.c.id == references["id"]).values(
                                gateway_device_id=references["gateway_device_id"], primary_link_id=references["primary_link_id"]))
                target_counts = {}
                for table in tables:
                    target_counts[table.name] = int((await destination.execute(select(func.count()).select_from(table))).scalar_one())
                mismatches = [name for name, count in source_counts.items() if target_counts.get(name) != count]
                if mismatches:
                    raise RuntimeError("Migration validation failed for: " + ", ".join(mismatches))
                await synchronize_generated_keys(destination, item.database_type, tables)
        finally:
            await source.close()

        # Confirm committed counts before changing the active database pointer.
        committed_counts = {}
        async with target.connect() as connection:
            for table in tables:
                committed_counts[table.name] = int((await connection.execute(select(func.count()).select_from(table))).scalar_one())
        mismatches = [name for name, count in source_counts.items() if committed_counts.get(name) != count]
        if mismatches: raise RuntimeError("Migration validation failed for: " + ", ".join(mismatches))

        settings = get_settings()
        activated_at = datetime.now(timezone.utc).isoformat()
        save_active_database(target_url, settings.SECRET_KEY, {"connection_id": item.id, "name": item.name,
            "database_type": item.database_type, "activated_at": activated_at}, previous_url=database.active_database_url,
            previous_metadata=database.active_database_metadata or {"name": "Banco padrão anterior",
                "database_type": "SQLITE" if database.active_database_url.startswith("sqlite") else "ENVIRONMENT"})
        return {"status": "READY", "restart_required": True, "connection_id": item.id,
            "database_name": item.name, "database_type": item.database_type,
            "migrated_records": sum(source_counts.values()), "tables_validated": len(source_counts), "activated_at": activated_at}
    finally:
        await target.dispose()
