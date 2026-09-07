from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import BigInteger, Integer, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database import _create_engine
from app.models.platform import DatabaseConnection
from app.security import decrypt_secret


DEFAULT_PORTS = {"POSTGRESQL": 5432, "MYSQL": 3306, "MSSQL": 1433, "ORACLE": 1521}


def build_database_url(item: DatabaseConnection) -> str:
    password = quote_plus(decrypt_secret(item.encrypted_password) or "")
    username = quote_plus(item.username or "")
    host = item.host or "localhost"
    if item.database_type == "SQLITE":
        if item.database_name == ":memory:": return "sqlite+aiosqlite:///:memory:"
        path = Path(item.database_name).expanduser().resolve()
        return f"sqlite+aiosqlite:///{path.as_posix()}"
    credentials = f"{username}:{password}@" if username or password else ""
    if item.database_type == "POSTGRESQL":
        ssl = "?ssl=require" if item.ssl_enabled else ""
        return f"postgresql+asyncpg://{credentials}{host}:{item.port or 5432}/{quote_plus(item.database_name)}{ssl}"
    if item.database_type == "MYSQL":
        ssl = "?ssl=true" if item.ssl_enabled else ""
        return f"mysql+asyncmy://{credentials}{host}:{item.port or 3306}/{quote_plus(item.database_name)}{ssl}"
    if item.database_type == "MSSQL":
        encryption = "&Encrypt=yes&TrustServerCertificate=no" if item.ssl_enabled else "&Encrypt=no"
        return f"mssql+aioodbc://{credentials}{host}:{item.port or 1433}/{quote_plus(item.database_name)}?driver=ODBC+Driver+18+for+SQL+Server{encryption}"
    if item.database_type == "ORACLE":
        protocol = "tcps" if item.ssl_enabled else "tcp"
        return f"oracle+oracledb_async://{credentials}{host}:{item.port or 1521}/?service_name={quote_plus(item.database_name)}&protocol={protocol}"
    raise ValueError("Unsupported database type")


def validation_query(database_type: str) -> str:
    return "SELECT 1 FROM DUAL" if database_type == "ORACLE" else "SELECT 1"


def limited_query(database_type: str, query: str) -> str:
    if database_type == "MSSQL": return f"SELECT TOP 100 * FROM ({query}) AS netmonitor_source"
    if database_type == "ORACLE": return f"SELECT * FROM ({query}) netmonitor_source FETCH FIRST 100 ROWS ONLY"
    return f"SELECT * FROM ({query}) AS netmonitor_source LIMIT 100"


async def test_authenticated_connection(item: DatabaseConnection) -> None:
    engine = _create_engine(build_database_url(item))
    try:
        async with engine.connect() as connection:
            await connection.execute(text(validation_query(item.database_type)))
    finally:
        await engine.dispose()


async def validate_database_url(url: str) -> None:
    engine = _create_engine(url)
    try:
        async with engine.connect() as connection:
            database_type = "ORACLE" if connection.dialect.name == "oracle" else "OTHER"
            await connection.execute(text(validation_query(database_type)))
    finally:
        await engine.dispose()


async def execute_read_only(item: DatabaseConnection, query: str, parameters: dict) -> list[dict]:
    engine = _create_engine(build_database_url(item))
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(limited_query(item.database_type, query)), parameters or {})
            return [dict(row._mapping) for row in result.fetchall()]
    finally:
        await engine.dispose()


def has_generated_integer_key(table) -> bool:
    if len(table.primary_key.columns) != 1: return False
    column = next(iter(table.primary_key.columns))
    return isinstance(column.type, (Integer, BigInteger)) and column.autoincrement is not False


async def before_table_insert(connection: AsyncConnection, database_type: str, table) -> None:
    if database_type == "MSSQL" and has_generated_integer_key(table):
        await connection.exec_driver_sql(f"SET IDENTITY_INSERT [{table.name}] ON")


async def after_table_insert(connection: AsyncConnection, database_type: str, table) -> None:
    if database_type == "MSSQL" and has_generated_integer_key(table):
        await connection.exec_driver_sql(f"SET IDENTITY_INSERT [{table.name}] OFF")


async def synchronize_generated_keys(connection: AsyncConnection, database_type: str, tables) -> None:
    for table in tables:
        if not has_generated_integer_key(table): continue
        pk = next(iter(table.primary_key.columns))
        maximum = int((await connection.execute(text(
            f'SELECT COALESCE(MAX("{pk.name.upper()}"), 0) FROM "{table.name.upper()}"'
            if database_type == "ORACLE" else
            f'SELECT COALESCE(MAX("{pk.name}"), 0) FROM "{table.name}"'
            if database_type == "POSTGRESQL" else
            f"SELECT COALESCE(MAX([{pk.name}]), 0) FROM [{table.name}]" if database_type == "MSSQL" else
            f"SELECT COALESCE(MAX(`{pk.name}`), 0) FROM `{table.name}`" if database_type == "MYSQL" else
            f'SELECT COALESCE(MAX("{pk.name}"), 0) FROM "{table.name}"'
        ))).scalar_one())
        next_value = maximum + 1
        if database_type == "POSTGRESQL":
            await connection.execute(text(
                "SELECT setval(pg_get_serial_sequence(:table_name, :column_name), :maximum, :has_rows)"
            ), {"table_name": table.name, "column_name": pk.name, "maximum": max(maximum, 1), "has_rows": maximum > 0})
        elif database_type == "MYSQL":
            # InnoDB advances AUTO_INCREMENT automatically when explicit IDs
            # are inserted. ALTER TABLE would implicitly commit the migration.
            continue
        elif database_type == "MSSQL":
            await connection.exec_driver_sql(f"DBCC CHECKIDENT ('{table.name}', RESEED, {maximum})")
        elif database_type == "ORACLE":
            sequence = (await connection.execute(text(
                "SELECT sequence_name FROM user_tab_identity_cols WHERE table_name = :table_name AND column_name = :column_name"
            ), {"table_name": table.name.upper(), "column_name": pk.name.upper()})).scalar_one_or_none()
            if sequence:
                try:
                    await connection.exec_driver_sql(f'ALTER SEQUENCE "{sequence}" RESTART START WITH {next_value}')
                except Exception:
                    current = int((await connection.execute(text(
                        "SELECT last_number FROM user_sequences WHERE sequence_name = :sequence_name"
                    ), {"sequence_name": sequence})).scalar_one())
                    if current >= next_value:
                        continue
                    # Older Oracle versions do not support RESTART. Advance the
                    # sequence to one value before the desired next identity;
                    # NEXTVAL used for synchronization is consumed here.
                    delta = (next_value - 1) - current
                    if delta:
                        await connection.exec_driver_sql(f'ALTER SEQUENCE "{sequence}" INCREMENT BY {delta}')
                    await connection.exec_driver_sql(f'SELECT "{sequence}".NEXTVAL FROM DUAL')
                    if delta:
                        await connection.exec_driver_sql(f'ALTER SEQUENCE "{sequence}" INCREMENT BY 1')
