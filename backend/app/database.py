from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings
from app.db_bootstrap import load_active_database

settings = get_settings()
active_database_url, active_database_metadata = load_active_database(settings.DATABASE_URL, settings.SECRET_KEY)
migration_in_progress = False

from sqlalchemy import event

def _create_engine(url: str):
    # SQL statement logging can expose credentials and personal data through
    # bound parameters, and is prohibitively noisy for monitoring workloads.
    kwargs = {"echo": False, "hide_parameters": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
    else:
        kwargs.update({"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20})
        if url.startswith("mysql"):
            kwargs["connect_args"] = {"init_command": "SET time_zone = '+00:00'"}
        elif url.startswith("postgresql"):
            kwargs["connect_args"] = {"server_settings": {"timezone": "UTC"}}
    eng = create_async_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            # SQLite does not enforce declared foreign keys unless this is
            # enabled for every connection. Without it, orphaned rows can be
            # created locally and later make a migration to stricter database
            # engines fail.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    return eng


engine = _create_engine(active_database_url)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def switch_runtime_engine(url: str, metadata: dict | None = None):
    global engine, active_database_url, active_database_metadata
    previous_engine = engine
    engine = _create_engine(url)
    active_database_url = url
    active_database_metadata = metadata
    async_session_factory.configure(bind=engine)
    await previous_engine.dispose()
    return engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
