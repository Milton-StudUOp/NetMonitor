import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Column, Identity, Integer, MetaData, Table, func, insert, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.engine import make_url

from app.services.database_adapters import (after_table_insert, before_table_insert,
    limited_query, synchronize_generated_keys)
from app.database import Base
from app.models.device import Device
from app.models.platform import DatabaseConnection
from app.security import encrypt_secret
from app.services.database_switcher import migrate_and_activate
import app.services.database_switcher as switcher


DATABASES = {
    "postgresql": "NETMONITOR_TEST_POSTGRESQL_URL",
    "mysql": "NETMONITOR_TEST_MYSQL_URL",
    "mssql": "NETMONITOR_TEST_MSSQL_URL",
    "oracle": "NETMONITOR_TEST_ORACLE_URL",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("database_type,environment_name", DATABASES.items())
async def test_real_database_authentication(database_type, environment_name):
    url = os.getenv(environment_name)
    if not url: pytest.skip(f"Set {environment_name} to run this integration test")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            query = "SELECT 1 FROM DUAL" if database_type == "oracle" else "SELECT 1"
            assert int((await connection.execute(text(query))).scalar_one()) == 1
            base_query = "SELECT :value AS status FROM DUAL" if database_type == "oracle" else "SELECT :value AS status"
            result = await connection.execute(text(limited_query(database_type.upper(), base_query)), {"value": 7})
            assert int(result.mappings().one()["status"]) == 7
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("database_type,environment_name", DATABASES.items())
async def test_real_identity_reseed_after_explicit_migration(database_type, environment_name):
    url = os.getenv(environment_name)
    if not url: pytest.skip(f"Set {environment_name} to run this integration test")
    table_name = f"nm_identity_{uuid.uuid4().hex[:12]}"
    metadata = MetaData()
    table = Table(table_name, metadata, Column("id", Integer, Identity(), primary_key=True))
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            await before_table_insert(connection, database_type.upper(), table)
            try: await connection.execute(insert(table).values(id=42))
            finally: await after_table_insert(connection, database_type.upper(), table)
            await synchronize_generated_keys(connection, database_type.upper(), [table])
            await connection.execute(insert(table).values({}))
            ids = list((await connection.execute(select(table.c.id).order_by(table.c.id))).scalars())
            assert ids == [42, 43]
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("database_type,environment_name", DATABASES.items())
async def test_full_migration_to_real_database(database_type, environment_name, tmp_path, monkeypatch):
    url_text = os.getenv(environment_name)
    if not url_text: pytest.skip(f"Set {environment_name} to run this integration test")
    if os.getenv("NETMONITOR_ALLOW_DESTRUCTIVE_DATABASE_TESTS") != "1":
        pytest.skip("Set NETMONITOR_ALLOW_DESTRUCTIVE_DATABASE_TESTS=1 only for a dedicated empty test database")
    url = make_url(url_text)
    source = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'migration-source.db').as_posix()}")
    target = create_async_engine(url_text)
    monkeypatch.setattr(switcher, "save_active_database", lambda *args, **kwargs: None)
    try:
        async with source.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(insert(Device.__table__).values(id=42, name="Migrated device",
                device_type="ROUTER", location="Integration test", monitoring_method="ICMP", snmp_port=161,
                is_critical=False, monitoring_interval=30, status="UNKNOWN"))
        async with target.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        item = DatabaseConnection(id=999, name=f"{database_type} integration", database_type=database_type.upper(),
            host=url.host, port=url.port, database_name=url.database or url.query.get("service_name"),
            username=url.username, encrypted_password=encrypt_secret(url.password or ""), enabled=True)
        result = await migrate_and_activate(source, item)
        assert result["tables_validated"] == len(Base.metadata.tables)
        async with target.begin() as connection:
            await connection.execute(insert(Device.__table__).values(name="Post migration device",
                device_type="SWITCH", location="Integration test", monitoring_method="ICMP", snmp_port=161,
                is_critical=False, monitoring_interval=30, status="UNKNOWN"))
            assert int((await connection.execute(select(func.max(Device.id)))).scalar_one()) == 43
    finally:
        async with target.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await source.dispose(); await target.dispose()
