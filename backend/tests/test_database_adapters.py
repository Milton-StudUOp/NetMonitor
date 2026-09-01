from unittest.mock import AsyncMock

import pytest

from app.models.platform import DatabaseConnection
from app.security import encrypt_secret
from app.models.device import Device
import app.models  # noqa: F401 - register every table in shared metadata
from app.database import Base
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.schema import CreateTable
from app.services.database_adapters import (after_table_insert, before_table_insert,
    build_database_url, limited_query, validation_query)
import app.db_bootstrap as bootstrap


@pytest.mark.parametrize("database_type,port,driver", [
    ("POSTGRESQL", 5432, "postgresql+asyncpg"),
    ("MYSQL", 3306, "mysql+asyncmy"),
    ("MSSQL", 1433, "mssql+aioodbc"),
    ("ORACLE", 1521, "oracle+oracledb_async"),
])
def test_database_urls_use_async_drivers(database_type, port, driver):
    item = DatabaseConnection(name=database_type, database_type=database_type, host="db.internal",
        port=port, database_name="network_monitor", username="netmonitor",
        encrypted_password=encrypt_secret("safe password"), ssl_enabled=False)
    url = build_database_url(item)
    assert url.startswith(driver)
    assert "safe password" not in url
    assert f":{port}/" in url


@pytest.mark.parametrize("database_type,expected", [
    ("SQLITE", "LIMIT 100"), ("POSTGRESQL", "LIMIT 100"), ("MYSQL", "LIMIT 100"),
    ("MSSQL", "TOP 100"), ("ORACLE", "FETCH FIRST 100 ROWS ONLY"),
])
def test_read_limit_is_dialect_specific(database_type, expected):
    assert expected in limited_query(database_type, "SELECT 1")


def test_oracle_validation_uses_dual():
    assert validation_query("ORACLE") == "SELECT 1 FROM DUAL"


@pytest.mark.asyncio
async def test_mssql_identity_insert_is_scoped_per_table():
    connection = AsyncMock()
    table = Device.__table__
    await before_table_insert(connection, "MSSQL", table)
    await after_table_insert(connection, "MSSQL", table)
    commands = [call.args[0] for call in connection.exec_driver_sql.await_args_list]
    assert commands == ["SET IDENTITY_INSERT [devices] ON", "SET IDENTITY_INSERT [devices] OFF"]


def test_encrypted_database_rollback_swaps_active_and_previous(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "BOOTSTRAP_FILE", tmp_path / ".active-database")
    bootstrap.save_active_database("postgresql+asyncpg://current", "secret", {"name": "Current", "database_type": "POSTGRESQL"},
        previous_url="sqlite+aiosqlite:///previous.db", previous_metadata={"name": "Previous", "database_type": "SQLITE"})
    result = bootstrap.rollback_active_database("secret")
    active_url, metadata = bootstrap.load_active_database("", "secret")
    assert result["restart_required"] is True
    assert active_url == "sqlite+aiosqlite:///previous.db"
    assert metadata["name"] == "Previous"
    assert "current" not in bootstrap.BOOTSTRAP_FILE.read_text(encoding="utf-8")


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect(), mysql.dialect(), mssql.dialect(), oracle.dialect()])
def test_every_model_compiles_for_every_supported_dialect(dialect):
    for table in Base.metadata.tables.values():
        assert str(CreateTable(table).compile(dialect=dialect))
