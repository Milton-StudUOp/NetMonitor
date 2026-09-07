from contextlib import asynccontextmanager
import logging
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, async_session_factory
import app.database as database
from app.schema_migrations import ensure_runtime_schema
from app.api import auth, devices, links, interfaces, redundancy, alerts, topology, reports, websocket, history, platform, discovery, system_health
from app.services.auth_service import authenticate_token
from app.services.monitoring_engine import monitoring_engine
from app.models import Device, DeviceType, DeviceStatus, Interface, InterfaceStatus, Link, LinkType, LinkPriority, LinkStatus, RedundancyGroup, RedundancyStatus

logger = structlog.get_logger()
settings = get_settings()

# Request access lines reveal routes, client addresses and traffic patterns.
# Security audit events remain persisted in the database instead.
logging.getLogger("uvicorn.access").disabled = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup")
    # Initialize DB tables
    # Never change the selected primary database implicitly. A migration or
    # connectivity failure must stop startup visibly; rollback remains an
    # explicit administrator operation and cannot expose a stale fallback DB.
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_runtime_schema(database.engine)

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
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {"/health", "/api/auth/login", "/api/auth/bootstrap", "/api/auth/forgot-password", "/api/auth/reset-password"}
SELF_SERVICE_PATHS = {"/api/auth/me", "/api/auth/logout", "/api/auth/change-password"}
OPERATOR_MUTATIONS = (
    ("PUT", "/api/alerts/"),
    ("POST", "/api/discovery/"),
    ("POST", "/api/devices"),
    ("PUT", "/api/devices/"),
    ("DELETE", "/api/devices/"),
)
ADMIN_ONLY_PREFIXES = ("/api/system-health", "/api/auth/users", "/api/platform/databases", "/api/platform/database-runtime", "/api/platform/data-sources", "/api/platform/notifications", "/api/platform/settings", "/api/platform/configuration", "/api/platform/audit")

@app.middleware("http")
async def authentication(request: Request, call_next):
    # CORS preflight never carries application credentials.
    if request.method == "OPTIONS" or settings.AUTH_DISABLED or request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail":"Authentication required"})
    async with async_session_factory() as db:
        authenticated = await authenticate_token(db, authorization[7:])
        if not authenticated:
            return JSONResponse(status_code=401, content={"detail":"Session is invalid or expired"})
        user, session = authenticated
        request.state.user = user
        request.state.auth_session = session
        # Protected handlers that mutate the authenticated account must reuse
        # this transaction. Opening a second session can deadlock on MySQL
        # while this authentication transaction remains active.
        request.state.auth_db = db
        if database.migration_in_progress and request.method not in {"GET", "HEAD", "OPTIONS"}:
            return JSONResponse(status_code=503, content={"detail":"Database migration is in progress; changes are temporarily disabled"})
        if user.must_change_password and request.url.path not in SELF_SERVICE_PATHS:
            return JSONResponse(status_code=403, content={"detail":"Password change required","code":"PASSWORD_CHANGE_REQUIRED"})
        if user.role != "ADMINISTRATOR" and any(request.url.path.startswith(prefix) for prefix in ADMIN_ONLY_PREFIXES):
            return JSONResponse(status_code=403, content={"detail":"Administrator permission required"})
        personal_topology_view = request.url.path.startswith("/api/platform/topology-layout/snapshots")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and user.role == "VIEWER" and request.url.path not in SELF_SERVICE_PATHS:
            if not personal_topology_view:
                return JSONResponse(status_code=403, content={"detail":"Viewer role is read-only"})
        if request.method not in {"GET", "HEAD", "OPTIONS"} and user.role == "OPERATOR" and request.url.path not in SELF_SERVICE_PATHS and not personal_topology_view and not any(request.method == method and request.url.path.startswith(prefix) for method,prefix in OPERATOR_MUTATIONS):
            return JSONResponse(status_code=403, content={"detail":"Administrator permission required"})
        response = await call_next(request)
        if getattr(request.state, "logout_requested", False):
            await db.delete(session)
        await db.commit()
        return response

# Include Routers
app.include_router(auth.router)
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
app.include_router(system_health.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Network Monitor Backend"}
# Trigger live reload
