from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine, async_session_factory
from app.schema_migrations import ensure_runtime_schema
from app.api import devices, links, interfaces, redundancy, alerts, topology, reports, websocket, history
from app.services.monitoring_engine import monitoring_engine
from app.models import Device, DeviceType, DeviceStatus, Interface, InterfaceStatus, Link, LinkType, LinkPriority, LinkStatus, RedundancyGroup, RedundancyStatus

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup")
    # Initialize DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_runtime_schema(engine)

    # Start background monitoring engine
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


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Network Monitor Backend"}
# Trigger live reload
