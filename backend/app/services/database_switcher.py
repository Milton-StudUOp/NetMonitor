from datetime import datetime, timezone
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings
from app.database import Base
import app.database as database
from app.db_bootstrap import save_active_database
from app.models.platform import DatabaseConnection
from app.services.database_adapters import (after_table_insert, before_table_insert,
    build_database_url, synchronize_generated_keys)


async def migrate_and_activate(source_engine: AsyncEngine, item: DatabaseConnection) -> dict:
    target_url = build_database_url(item)
    target = create_async_engine(target_url, pool_pre_ping=True)
    try:
        async with target.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        priority = ["icon_assets", "devices", "interfaces", "links", "redundancy_groups",
            "database_connections", "database_data_sources", "notification_integrations",
            "notification_rules", "notification_deliveries", "topology_positions", "topology_snapshots", "system_settings", "monitoring_results",
            "alerts", "audit_logs"]
        tables_by_name = Base.metadata.tables
        tables = [tables_by_name[name] for name in priority if name in tables_by_name]
        tables.extend(table for name, table in tables_by_name.items() if name not in priority)
        source_counts = {}
        async with source_engine.connect() as source:
            for table in tables:
                source_counts[table.name] = int((await source.execute(select(func.count()).select_from(table))).scalar_one())

        async with target.connect() as connection:
            populated = []
            for table in tables:
                count = int((await connection.execute(select(func.count()).select_from(table))).scalar_one())
                if count: populated.append(table.name)
        if populated:
            raise ValueError("Target database is not empty: " + ", ".join(populated[:8]))

        async with target.begin() as destination, source_engine.connect() as source:
            deferred_device_references = []
            for table in tables:
                rows = [dict(row._mapping) for row in (await source.execute(select(table))).all()]
                if table.name == "devices":
                    deferred_device_references = [{"id": row["id"], "gateway_device_id": row.get("gateway_device_id"), "primary_link_id": row.get("primary_link_id")} for row in rows]
                    rows = [{**row, "gateway_device_id": None, "primary_link_id": None} for row in rows]
                if rows:
                    await before_table_insert(destination, item.database_type, table)
                    try: await destination.execute(insert(table), rows)
                    finally: await after_table_insert(destination, item.database_type, table)
            devices = tables_by_name.get("devices")
            if devices is not None:
                for references in deferred_device_references:
                    if references["gateway_device_id"] is not None or references["primary_link_id"] is not None:
                        await destination.execute(update(devices).where(devices.c.id == references["id"]).values(
                            gateway_device_id=references["gateway_device_id"], primary_link_id=references["primary_link_id"]))
            await synchronize_generated_keys(destination, item.database_type, tables)

        target_counts = {}
        async with target.connect() as connection:
            for table in tables:
                target_counts[table.name] = int((await connection.execute(select(func.count()).select_from(table))).scalar_one())
        mismatches = [name for name, count in source_counts.items() if target_counts.get(name) != count]
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
