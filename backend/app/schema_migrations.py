from sqlalchemy import inspect


async def ensure_runtime_schema(engine) -> None:
    """Apply tiny compatibility migrations for deployments without Alembic versions."""
    async with engine.begin() as conn:
        device_columns = await conn.run_sync(
            lambda sync_conn: {col["name"] for col in inspect(sync_conn).get_columns("devices")}
        )
        dialect = conn.dialect.name

        if "gateway_ip_address" not in device_columns:
            await conn.exec_driver_sql(_add_column_sql(dialect, "devices", "gateway_ip_address", "VARCHAR(45)"))
        if "gateway_device_id" not in device_columns:
            await conn.exec_driver_sql(_add_column_sql(dialect, "devices", "gateway_device_id", "INTEGER"))
        if "primary_link_id" not in device_columns:
            await conn.exec_driver_sql(_add_column_sql(dialect, "devices", "primary_link_id", "INTEGER"))
        if "group_name" not in device_columns:
            await conn.exec_driver_sql(_add_column_sql(dialect, "devices", "group_name", "VARCHAR(128)"))
        if "icon_id" not in device_columns:
            await conn.exec_driver_sql(_add_column_sql(dialect, "devices", "icon_id", "INTEGER"))
        if "monitoring_method" not in device_columns:
            await conn.exec_driver_sql(_add_column_sql(dialect, "devices", "monitoring_method", "VARCHAR(24) DEFAULT 'ICMP'"))

        redundancy_columns = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("redundancy_groups")
        )
        redundancy_by_name = {column["name"]: column for column in redundancy_columns}
        needs_redundancy_upgrade = (
            "redundancy_type" not in redundancy_by_name
            or "primary_device_id" not in redundancy_by_name
            or "secondary_device_id" not in redundancy_by_name
            or not redundancy_by_name["primary_link_id"]["nullable"]
            or not redundancy_by_name["secondary_link_id"]["nullable"]
        )
        if needs_redundancy_upgrade:
            if dialect == "sqlite":
                await _upgrade_sqlite_redundancy_groups(conn, redundancy_by_name)
            else:
                if "redundancy_type" not in redundancy_by_name:
                    await conn.exec_driver_sql(
                        _add_column_sql(dialect, "redundancy_groups", "redundancy_type", "VARCHAR(16) DEFAULT 'LINK' NOT NULL")
                    )
                if "primary_device_id" not in redundancy_by_name:
                    await conn.exec_driver_sql(
                        _add_column_sql(dialect, "redundancy_groups", "primary_device_id", "INTEGER")
                    )
                if "secondary_device_id" not in redundancy_by_name:
                    await conn.exec_driver_sql(
                        _add_column_sql(dialect, "redundancy_groups", "secondary_device_id", "INTEGER")
                    )
                if dialect == "postgresql":
                    await conn.exec_driver_sql(
                        "ALTER TABLE redundancy_groups ALTER COLUMN primary_link_id DROP NOT NULL"
                    )
                    await conn.exec_driver_sql(
                        "ALTER TABLE redundancy_groups ALTER COLUMN secondary_link_id DROP NOT NULL"
                    )
                elif dialect in {"mysql", "mariadb"}:
                    await conn.exec_driver_sql("ALTER TABLE redundancy_groups MODIFY COLUMN primary_link_id INTEGER NULL")
                    await conn.exec_driver_sql("ALTER TABLE redundancy_groups MODIFY COLUMN secondary_link_id INTEGER NULL")
                elif dialect == "mssql":
                    await conn.exec_driver_sql("ALTER TABLE redundancy_groups ALTER COLUMN primary_link_id INTEGER NULL")
                    await conn.exec_driver_sql("ALTER TABLE redundancy_groups ALTER COLUMN secondary_link_id INTEGER NULL")
                elif dialect == "oracle":
                    await conn.exec_driver_sql("ALTER TABLE redundancy_groups MODIFY (primary_link_id NULL)")
                    await conn.exec_driver_sql("ALTER TABLE redundancy_groups MODIFY (secondary_link_id NULL)")


def _add_column_sql(dialect: str, table_name: str, column_name: str, column_type: str) -> str:
    if dialect == "postgresql":
        return f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
    return f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"


async def _upgrade_sqlite_redundancy_groups(conn, columns: dict) -> None:
    """Rebuild the SQLite table because SQLite cannot drop NOT NULL in place."""
    await conn.exec_driver_sql(
        """
        CREATE TABLE redundancy_groups_v2 (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(128) NOT NULL UNIQUE,
            description TEXT,
            redundancy_type VARCHAR(16) NOT NULL DEFAULT 'LINK',
            primary_link_id INTEGER,
            secondary_link_id INTEGER,
            primary_device_id INTEGER,
            secondary_device_id INTEGER,
            status VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN',
            service_check_type VARCHAR(16) NOT NULL DEFAULT 'NONE',
            service_check_target VARCHAR(256),
            service_check_port INTEGER,
            last_evaluated DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            FOREIGN KEY(primary_link_id) REFERENCES links (id),
            FOREIGN KEY(secondary_link_id) REFERENCES links (id),
            FOREIGN KEY(primary_device_id) REFERENCES devices (id),
            FOREIGN KEY(secondary_device_id) REFERENCES devices (id)
        )
        """
    )
    redundancy_type = "redundancy_type" if "redundancy_type" in columns else "'LINK'"
    primary_device = "primary_device_id" if "primary_device_id" in columns else "NULL"
    secondary_device = "secondary_device_id" if "secondary_device_id" in columns else "NULL"
    await conn.exec_driver_sql(
        f"""
        INSERT INTO redundancy_groups_v2 (
            id, name, description, redundancy_type,
            primary_link_id, secondary_link_id, primary_device_id, secondary_device_id,
            status, service_check_type, service_check_target, service_check_port,
            last_evaluated, created_at, updated_at
        )
        SELECT
            id, name, description, {redundancy_type},
            primary_link_id, secondary_link_id, {primary_device}, {secondary_device},
            status, service_check_type, service_check_target, service_check_port,
            last_evaluated, created_at, updated_at
        FROM redundancy_groups
        """
    )
    await conn.exec_driver_sql("DROP TABLE redundancy_groups")
    await conn.exec_driver_sql("ALTER TABLE redundancy_groups_v2 RENAME TO redundancy_groups")
    await conn.exec_driver_sql(
        "CREATE INDEX ix_redundancy_groups_name ON redundancy_groups (name)"
    )
