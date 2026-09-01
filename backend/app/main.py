from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, async_session_factory
import app.database as database
from app.db_bootstrap import get_previous_database, rollback_active_database
from app.schema_migrations import ensure_runtime_schema
from app.api import devices, links, interfaces, redundancy, alerts, topology, reports, websocket, history, platform, discovery
from app.services.monitoring_engine import monitoring_engine
from app.models import Device, DeviceType, DeviceStatus, Interface, InterfaceStatus, Link, LinkType, LinkPriority, LinkStatus, RedundancyGroup, RedundancyStatus

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup")
    # Initialize DB tables
    try:
        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await ensure_runtime_schema(database.engine)
    except Exception as startup_error:
        previous = get_previous_database(settings.SECRET_KEY)
        if not previous:
            raise
        logger.error("primary_database_startup_failed_rolling_back", error=type(startup_error).__name__)
        rollback = rollback_active_database(settings.SECRET_KEY)
        await database.switch_runtime_engine(previous[0], {"connection_id": None, "name": rollback["name"],
            "database_type": rollback["database_type"], "activated_at": rollback["activated_at"],
            "rollback_available": True})
        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await ensure_runtime_schema(database.engine)
        logger.warning("primary_database_rollback_completed", database=rollback["name"])

    # Start background monitoring engine
    await monitoring_engine.load_configuration()
    monitoring_engine.start()

    yield

    logger.info("application_shutdown")
    monitoring_engine.stop()


app = FastAPI(
    title="Network Link & Redundancy Monitoring System",
    version="1.0.0",
    description="Real-time network monitoring system with topology-aware redundancy degradation detection.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(devices.router)
app.include_router(links.router)
app.include_router(interfaces.router)
app.include_router(redundancy.router)
app.include_router(alerts.router)
app.include_router(topology.router)
app.include_router(reports.router)
app.include_router(history.router)
app.include_router(websocket.router)
app.include_router(platform.router)
app.include_router(discovery.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Network Monitor Backend"}
# Trigger live reload
