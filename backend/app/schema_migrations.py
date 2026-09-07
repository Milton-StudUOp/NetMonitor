from sqlalchemy import inspect

SCHEMA_VERSION = 2


async def ensure_runtime_schema(engine) -> None:
    """Apply tiny compatibility migrations for deployments without Alembic versions."""
    async with engine.begin() as conn:
        device_columns = await conn.run_sync(
            lambda sync_conn: {col["name"] for col in inspect(sync_conn).get_columns("devices")}
        )
        dialect = conn.dialect.name

        user_columns = await conn.run_sync(
            lambda sync_conn: {col["name"] for col in inspect(sync_conn).get_columns("user_accounts")}
        )
        if "email" not in user_columns:
            await conn.exec_driver_sql(_add_column_sql(dialect, "user_accounts", "email", "VARCHAR(320)"))
        user_indexes = await conn.run_sync(
            lambda sync_conn: {index["name"]: index for index in inspect(sync_conn).get_indexes("user_accounts")}
        )
        email_index = user_indexes.get("ix_user_accounts_email")
        if not email_index or not email_index.get("unique"):
            duplicate_email = (await conn.exec_driver_sql(
                "SELECT email FROM user_accounts WHERE email IS NOT NULL GROUP BY email HAVING COUNT(*) > 1"
            )).first()
            if duplicate_email:
                raise RuntimeError("Duplicate user emails must be resolved before applying the unique email constraint")
            if email_index:
                await conn.exec_driver_sql(_drop_index_sql(dialect, "ix_user_accounts_email", "user_accounts"))
            await conn.exec_driver_sql("CREATE UNIQUE INDEX ix_user_accounts_email ON user_accounts (email)")
        if "must_change_password" not in user_columns:
            boolean_type = "NUMBER(1) DEFAULT 0 NOT NULL" if dialect == "oracle" else (
                "BIT DEFAULT 0 NOT NULL" if dialect == "mssql" else
                "BOOLEAN DEFAULT FALSE NOT NULL" if dialect == "postgresql" else
                "BOOLEAN DEFAULT 0 NOT NULL"
            )
            await conn.exec_driver_sql(_add_column_sql(dialect, "user_accounts", "must_change_password", boolean_type))

        snapshot_columns = await conn.run_sync(
            lambda sync_conn: {col["name"] for col in inspect(sync_conn).get_columns("topology_snapshots")}
        )
        if "user_id" not in snapshot_columns:
            await conn.exec_driver_sql(_add_column_sql(dialect, "topology_snapshots", "user_id", "INTEGER"))
        snapshot_indexes = await conn.run_sync(
            lambda sync_conn: {index["name"]: index for index in inspect(sync_conn).get_indexes("topology_snapshots")}
        )
        snapshot_constraints = await conn.run_sync(
            lambda sync_conn: {constraint.get("name") for constraint in inspect(sync_conn).get_unique_constraints("topology_snapshots")}
        )
        legacy_name_index = snapshot_indexes.get("ix_topology_snapshots_name")
        legacy_name_index_dropped = False
        if legacy_name_index and legacy_name_index.get("unique"):
            await conn.exec_driver_sql(_drop_index_sql(dialect, "ix_topology_snapshots_name", "topology_snapshots"))
            legacy_name_index_dropped = True
        if not legacy_name_index or legacy_name_index_dropped:
            await conn.exec_driver_sql("CREATE INDEX ix_topology_snapshots_name ON topology_snapshots (name)")
        if "ix_topology_snapshots_user_id" not in snapshot_indexes:
            await conn.exec_driver_sql("CREATE INDEX ix_topology_snapshots_user_id ON topology_snapshots (user_id)")
        if "uq_topology_snapshots_user_name" not in snapshot_indexes and "uq_topology_snapshots_user_name" not in snapshot_constraints:
            await conn.exec_driver_sql("CREATE UNIQUE INDEX uq_topology_snapshots_user_name ON topology_snapshots (user_id, name)")
        snapshot_foreign_keys = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("topology_snapshots")
        )
        has_snapshot_owner_fk = any(
            foreign_key.get("constrained_columns") == ["user_id"]
            and foreign_key.get("referred_table") == "user_accounts"
            for foreign_key in snapshot_foreign_keys
        )
        if not has_snapshot_owner_fk and dialect != "sqlite":
            await conn.exec_driver_sql(
                "ALTER TABLE topology_snapshots ADD CONSTRAINT fk_topology_snapshots_user_id "
                "FOREIGN KEY (user_id) REFERENCES user_accounts (id) ON DELETE CASCADE"
            )

        monitoring_indexes = await conn.run_sync(
            lambda sync_conn: {index["name"] for index in inspect(sync_conn).get_indexes("monitoring_results")}
        )
        if "ix_monitoring_result_target_time" not in monitoring_indexes:
            await conn.exec_driver_sql(
                "CREATE INDEX ix_monitoring_result_target_time ON monitoring_results (target_type, target_id, timestamp)"
            )
        if "ix_monitoring_result_status_time" not in monitoring_indexes:
            await conn.exec_driver_sql(
                "CREATE INDEX ix_monitoring_result_status_time ON monitoring_results (status, timestamp)"
            )

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

        version_row = (await conn.exec_driver_sql(
            "SELECT version FROM database_schema_versions WHERE id = 1"
        )).first()
        if version_row and int(version_row[0]) > SCHEMA_VERSION:
            raise RuntimeError("Database schema is newer than this application version")
        if version_row:
            await conn.exec_driver_sql(
                f"UPDATE database_schema_versions SET version = {SCHEMA_VERSION}, updated_at = CURRENT_TIMESTAMP WHERE id = 1"
            )
        else:
            await conn.exec_driver_sql(
                f"INSERT INTO database_schema_versions (id, version) VALUES (1, {SCHEMA_VERSION})"
            )


def _add_column_sql(dialect: str, table_name: str, column_name: str, column_type: str) -> str:
    if dialect == "postgresql":
        return f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
    return f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"


def _drop_index_sql(dialect: str, index_name: str, table_name: str) -> str:
    if dialect in {"mysql", "mariadb", "mssql"}:
        return f"DROP INDEX {index_name} ON {table_name}"
    return f"DROP INDEX {index_name}"


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
