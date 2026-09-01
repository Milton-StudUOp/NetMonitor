import asyncio
import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import DateTime as SQLDateTime, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
import app.database as database
from app.models.device import Device
from app.models.interface import Interface
from app.models.link import Link
from app.models.platform import (AuditLog, DatabaseConnection, DatabaseDataSource, IconAsset,
    NotificationIntegration, NotificationRule, SystemSetting, TopologyPosition, TopologySnapshot)
from app.models.redundancy_group import RedundancyGroup
from app.schemas.platform import (DatabaseConnectionInput, DatabaseConnectionRead, DatabaseDataSourceInput, DatabaseDataSourceRead,
    IconRead, NotificationIntegrationInput, NotificationIntegrationRead,
    NotificationRuleInput, NotificationRuleRead, SystemSettingsInput, TopologyLayoutInput, TopologySnapshotInput)
from app.security import decrypt_secret, encrypt_secret
from app.services.database_switcher import migrate_and_activate
from app.services.database_adapters import execute_read_only, test_authenticated_connection, validate_database_url
from app.db_bootstrap import get_previous_database, rollback_active_database
from app.services.notification.channels import safe_delivery_error, send_notification, validate_integration

router = APIRouter(prefix="/api/platform", tags=["Platform configuration"])
BUILTIN_ICONS = [
    ("router", "Router", "Network", "Router"), ("switch", "Switch", "Network", "Network"),
    ("firewall", "Firewall", "Network", "Shield"), ("access-point", "Access Point", "Network", "Wifi"),
    ("load-balancer", "Load Balancer", "Network", "GitFork"),
    ("server", "Physical Server", "Server", "Server"), ("vm", "Virtual Machine", "Server", "Box"),
    ("database", "Database Server", "Server", "Database"),
    ("radio", "Radio", "Communication", "Radio"), ("modem", "Modem", "Communication", "Router"),
    ("satellite", "Satellite", "Communication", "Satellite"),
    ("ups", "UPS", "Infrastructure", "BatteryCharging"), ("rack", "Rack", "Infrastructure", "PanelsTopLeft"),
]


async def _audit(db: AsyncSession, action: str, entity: str, entity_id, summary: str):
    db.add(AuditLog(action=action, entity_type=entity, entity_id=str(entity_id) if entity_id else None, summary=summary[:500]))


async def ensure_builtin_icons(db: AsyncSession):
    existing = set((await db.execute(select(IconAsset.key))).scalars().all())
    for key, name, category, lucide in BUILTIN_ICONS:
        if key not in existing:
            db.add(IconAsset(key=key, name=name, category=category, lucide_name=lucide, is_builtin=True))
    await db.flush()


@router.get("/icons", response_model=list[IconRead])
async def list_icons(db: AsyncSession = Depends(get_db)):
    await ensure_builtin_icons(db)
    return (await db.execute(select(IconAsset).order_by(IconAsset.category, IconAsset.name))).scalars().all()


@router.post("/icons", response_model=IconRead, status_code=201)
async def upload_icon(name: str = Form(...), category: str = Form("Custom"), file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    if len(content) > 512 * 1024:
        raise HTTPException(413, "Icon must not exceed 512 KB")
    mime = (file.content_type or "").lower()
    if mime not in {"image/svg+xml", "image/png"}:
        raise HTTPException(400, "Only SVG and PNG icons are supported")
    if mime == "image/svg+xml":
        text = content.decode("utf-8", errors="strict")
        lowered = text.lower()
        if "<script" in lowered or "javascript:" in lowered or "<!entity" in lowered:
            raise HTTPException(400, "Unsafe SVG content")
        data = text
    else:
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(400, "Invalid PNG file")
        data = base64.b64encode(content).decode("ascii")
    icon = IconAsset(key=f"custom-{int(datetime.now().timestamp() * 1000)}", name=name[:100], category=category[:40], custom_data=data, mime_type=mime, is_builtin=False)
    db.add(icon); await db.flush(); await _audit(db, "CREATE", "ICON", icon.id, f"Custom icon {name} uploaded")
    return icon


def _db_read(item: DatabaseConnection) -> DatabaseConnectionRead:
    return DatabaseConnectionRead.model_validate(item, from_attributes=True).model_copy(update={"password_configured": bool(item.encrypted_password)})


@router.get("/databases", response_model=list[DatabaseConnectionRead])
async def list_databases(db: AsyncSession = Depends(get_db)):
    return [_db_read(x) for x in (await db.execute(select(DatabaseConnection).order_by(DatabaseConnection.name))).scalars()]


@router.get("/database-runtime")
async def database_runtime():
    if database.active_database_metadata:
        return {"mode": "CONFIGURED", **database.active_database_metadata, "restart_pending": False}
    return {"mode": "DEFAULT", "connection_id": None, "name": "SQLite local",
        "database_type": "SQLITE" if database.active_database_url.startswith("sqlite") else "ENVIRONMENT",
        "activated_at": None, "restart_pending": False}


@router.post("/database-runtime/rollback")
async def rollback_database_runtime():
    from app.config import get_settings
    settings = get_settings(); previous = get_previous_database(settings.SECRET_KEY)
    if not previous: raise HTTPException(404, "No previous database is available")
    try: await asyncio.wait_for(validate_database_url(previous[0]), timeout=10)
    except Exception as exc: raise HTTPException(409, "Previous database could not be reached or authenticated") from exc
    return rollback_active_database(settings.SECRET_KEY)


@router.post("/databases/{item_id}/activate")
async def activate_database(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(DatabaseConnection, item_id)
    if not item: raise HTTPException(404, "Database connection not found")
    if not item.enabled: raise HTTPException(400, "Enable the connection before making it primary")
    try:
        await _test_database(item)
        await _audit(db, "MIGRATION_STARTED", "DATABASE", item.id, f"Migration to {item.name} started")
        await db.commit()
        result = await migrate_and_activate(database.engine, item)
        return result
    except Exception as exc:
        safe_reason = "The target is unavailable, not empty, lacks a compatible driver, or migration validation failed."
        await _audit(db, "MIGRATION_FAILED", "DATABASE", item.id, f"Migration to {item.name} failed")
        await db.commit()
        raise HTTPException(409, safe_reason) from exc


@router.post("/databases", response_model=DatabaseConnectionRead, status_code=201)
async def create_database(data: DatabaseConnectionInput, db: AsyncSession = Depends(get_db)):
    values = data.model_dump(exclude={"password"}); values["encrypted_password"] = encrypt_secret(data.password)
    item = DatabaseConnection(**values); db.add(item); await db.flush(); await _audit(db, "CREATE", "DATABASE", item.id, f"Database connection {item.name} created")
    return _db_read(item)


@router.put("/databases/{item_id}", response_model=DatabaseConnectionRead)
async def update_database(item_id: int, data: DatabaseConnectionInput, db: AsyncSession = Depends(get_db)):
    item = await db.get(DatabaseConnection, item_id)
    if not item: raise HTTPException(404, "Database connection not found")
    for key, value in data.model_dump(exclude={"password"}).items(): setattr(item, key, value)
    if data.password: item.encrypted_password = encrypt_secret(data.password)
    await _audit(db, "UPDATE", "DATABASE", item.id, f"Database connection {item.name} updated")
    return _db_read(item)


@router.delete("/databases/{item_id}", status_code=204)
async def delete_database(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(DatabaseConnection, item_id)
    if not item: raise HTTPException(404, "Database connection not found")
    await _audit(db, "DELETE", "DATABASE", item.id, f"Database connection {item.name} deleted"); await db.delete(item)


async def _test_database(item: DatabaseConnection):
    await asyncio.wait_for(test_authenticated_connection(item), timeout=10)


@router.post("/databases/{item_id}/test")
async def test_database(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(DatabaseConnection, item_id)
    if not item: raise HTTPException(404, "Database connection not found")
    try:
        await _test_database(item); item.last_status = "SUCCESS"; item.last_error = None
    except Exception:
        item.last_status = "FAILED"; item.last_error = "Unable to connect to database host. Verify host, port, SSL and credentials."
    item.last_tested_at = datetime.now(timezone.utc); await _audit(db, "TEST", "DATABASE", item.id, f"Connection test: {item.last_status}")
    return {"status": item.last_status, "message": item.last_error or "Connection established successfully."}


@router.get("/data-sources", response_model=list[DatabaseDataSourceRead])
async def list_data_sources(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(DatabaseDataSource).order_by(DatabaseDataSource.name))).scalars().all()


@router.post("/data-sources", response_model=DatabaseDataSourceRead, status_code=201)
async def create_data_source(data: DatabaseDataSourceInput, db: AsyncSession = Depends(get_db)):
    if not await db.get(DatabaseConnection, data.connection_id): raise HTTPException(400, "Database connection not found")
    item = DatabaseDataSource(**data.model_dump()); db.add(item); await db.flush(); await _audit(db, "CREATE", "DATA_SOURCE", item.id, f"Data source {item.name} created"); return item


@router.delete("/data-sources/{item_id}", status_code=204)
async def delete_data_source(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(DatabaseDataSource, item_id)
    if not item: raise HTTPException(404, "Data source not found")
    await _audit(db, "DELETE", "DATA_SOURCE", item.id, f"Data source {item.name} deleted"); await db.delete(item)


async def _execute_data_source(source: DatabaseDataSource, connection: DatabaseConnection):
    return await asyncio.wait_for(execute_read_only(connection, source.query_text, source.parameters or {}), timeout=15)


@router.post("/data-sources/{item_id}/test")
async def test_data_source(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(DatabaseDataSource, item_id)
    if not item: raise HTTPException(404, "Data source not found")
    connection = await db.get(DatabaseConnection, item.connection_id)
    try:
        rows = await _execute_data_source(item, connection); item.last_status = "SUCCESS"; item.last_error = None
        result = {"status": "SUCCESS", "row_count": len(rows), "rows": rows}
    except Exception:
        item.last_status = "FAILED"; item.last_error = "Read-only query failed. Verify syntax, parameters and permissions."
        result = {"status": "FAILED", "row_count": 0, "rows": [], "message": item.last_error}
    item.last_tested_at = datetime.now(timezone.utc); await _audit(db, "TEST", "DATA_SOURCE", item.id, f"Data source test: {item.last_status}"); return result


def _integration_read(item: NotificationIntegration) -> NotificationIntegrationRead:
    secrets = json.loads(decrypt_secret(item.encrypted_secrets) or "{}")
    return NotificationIntegrationRead(id=item.id, provider=item.provider, name=item.name, enabled=item.enabled,
        config=item.public_config or {}, secrets_configured=sorted(k for k, v in secrets.items() if v),
        last_status=item.last_status, last_error=item.last_error, last_tested_at=item.last_tested_at)


@router.get("/notifications", response_model=list[NotificationIntegrationRead])
async def list_notifications(db: AsyncSession = Depends(get_db)):
    return [_integration_read(x) for x in (await db.execute(select(NotificationIntegration).order_by(NotificationIntegration.provider))).scalars()]


@router.put("/notifications/{provider}", response_model=NotificationIntegrationRead)
async def save_notification(provider: str, data: NotificationIntegrationInput, db: AsyncSession = Depends(get_db)):
    provider = provider.upper()
    if provider != data.provider: raise HTTPException(400, "Provider path and payload do not match")
    item = (await db.execute(select(NotificationIntegration).where(NotificationIntegration.provider == provider))).scalar_one_or_none()
    if not item: item = NotificationIntegration(provider=provider, name=data.name); db.add(item)
    existing = json.loads(decrypt_secret(item.encrypted_secrets) or "{}")
    existing.update({k: v for k, v in data.secrets.items() if v})
    config = dict(data.config)
    if provider == "TELEGRAM" and config.get("chat_ids"):
        config.pop("chat_id", None)
    if provider == "WHATSAPP" and config.get("recipients"):
        config.pop("recipient", None)
    if data.enabled:
        try:
            validate_integration(provider, config, existing)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    item.name, item.enabled, item.public_config = data.name, data.enabled, config
    item.encrypted_secrets = encrypt_secret(json.dumps(existing))
    item.last_status, item.last_error = "UNTESTED", None
    await db.flush(); await _audit(db, "UPSERT", "NOTIFICATION", item.id, f"{provider} integration saved")
    return _integration_read(item)


async def _send_notification_test(item: NotificationIntegration):
    await send_notification(
        item,
        title="NetMonitor notification test",
        message="The test message was delivered successfully. NetMonitor can use this channel for operational incidents and recovery notifications.",
        severity="INFORMATION",
        context={
            "event_type": "CONFIGURATION_TEST", "target": item.name,
            "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )


@router.post("/notifications/{provider}/test")
async def test_notification(provider: str, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(NotificationIntegration).where(NotificationIntegration.provider == provider.upper()))).scalar_one_or_none()
    if not item: raise HTTPException(404, "Notification integration not found")
    try:
        await _send_notification_test(item); item.last_status = "SUCCESS"; item.last_error = None
    except Exception as exc:
        item.last_status = "FAILED"; item.last_error = safe_delivery_error(exc)
    item.last_tested_at = datetime.now(timezone.utc); await _audit(db, "TEST", "NOTIFICATION", item.id, f"{item.provider} test: {item.last_status}")
    return {"status": item.last_status, "message": item.last_error or "Test notification sent."}


@router.get("/notification-rules", response_model=list[NotificationRuleRead])
async def list_rules(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(NotificationRule).order_by(NotificationRule.name))).scalars().all()


@router.post("/notification-rules", response_model=NotificationRuleRead, status_code=201)
async def create_rule(data: NotificationRuleInput, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(NotificationRule).where(NotificationRule.name == data.name))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "A notification rule with this name already exists")
    item = NotificationRule(**data.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    await _audit(db, "CREATE", "NOTIFICATION_RULE", item.id, f"Rule {item.name} created")
    return NotificationRuleRead.model_validate(item)


@router.put("/notification-rules/{item_id}", response_model=NotificationRuleRead)
async def update_rule(item_id: int, data: NotificationRuleInput, db: AsyncSession = Depends(get_db)):
    item = await db.get(NotificationRule, item_id)
    if not item: raise HTTPException(404, "Notification rule not found")
    duplicate = (await db.execute(select(NotificationRule).where(
        NotificationRule.name == data.name, NotificationRule.id != item_id
    ))).scalar_one_or_none()
    if duplicate:
        raise HTTPException(409, "A notification rule with this name already exists")
    for k, v in data.model_dump().items(): setattr(item, k, v)
    await db.flush()
    await db.refresh(item)
    await _audit(db, "UPDATE", "NOTIFICATION_RULE", item.id, f"Rule {item.name} updated")
    return NotificationRuleRead.model_validate(item)


@router.delete("/notification-rules/{item_id}", status_code=204)
async def delete_rule(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(NotificationRule, item_id)
    if not item: raise HTTPException(404, "Notification rule not found")
    await _audit(db, "DELETE", "NOTIFICATION_RULE", item.id, f"Rule {item.name} deleted"); await db.delete(item)


@router.get("/topology-layout")
async def get_layout(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(TopologyPosition))).scalars().all()
    mode = (await db.get(SystemSetting, "topology"))
    return {"layout_mode": (mode.value or {}).get("layout_mode", "auto") if mode else "auto", "positions": [{"device_id": x.device_id, "x": x.x, "y": x.y} for x in rows]}


@router.put("/topology-layout")
async def save_layout(data: TopologyLayoutInput, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(TopologyPosition))
    db.add_all([TopologyPosition(device_id=x.device_id, x=x.x, y=x.y, layout_mode=data.layout_mode) for x in data.positions])
    setting = await db.get(SystemSetting, "topology") or SystemSetting(key="topology"); setting.value = {"layout_mode": data.layout_mode}; db.add(setting)
    await _audit(db, "UPDATE", "TOPOLOGY", None, f"Saved {len(data.positions)} node positions")
    return {"status": "saved", "count": len(data.positions)}


@router.get("/topology-layout/snapshots")
async def list_topology_snapshots(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(TopologySnapshot).order_by(TopologySnapshot.updated_at.desc()))).scalars().all()
    return [{"id": row.id, "name": row.name, "layout_mode": row.layout_mode,
        "positions": row.positions or [], "viewport": row.viewport or {},
        "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]


@router.post("/topology-layout/snapshots", status_code=201)
async def save_topology_snapshot(data: TopologySnapshotInput, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(TopologySnapshot).where(TopologySnapshot.name == data.name))).scalar_one_or_none()
    positions = [position.model_dump() for position in data.positions]
    if item:
        item.layout_mode, item.positions, item.viewport = data.layout_mode, positions, data.viewport
    else:
        item = TopologySnapshot(name=data.name, layout_mode=data.layout_mode, positions=positions, viewport=data.viewport); db.add(item)
    await db.flush(); await _audit(db, "UPSERT", "TOPOLOGY_SNAPSHOT", item.id, f"Topology view {item.name} saved")
    return {"id": item.id, "name": item.name, "layout_mode": item.layout_mode,
        "positions": item.positions, "viewport": item.viewport}


@router.put("/topology-layout/snapshots/{snapshot_id}")
async def update_topology_snapshot(snapshot_id: int, data: TopologySnapshotInput, db: AsyncSession = Depends(get_db)):
    item = await db.get(TopologySnapshot, snapshot_id)
    if not item: raise HTTPException(404, "Topology view not found")
    duplicate = (await db.execute(select(TopologySnapshot).where(
        TopologySnapshot.name == data.name, TopologySnapshot.id != snapshot_id,
    ))).scalar_one_or_none()
    if duplicate: raise HTTPException(409, "Another topology view already uses this name")
    item.name = data.name
    item.layout_mode = data.layout_mode
    item.positions = [position.model_dump() for position in data.positions]
    item.viewport = data.viewport
    await db.flush()
    await _audit(db, "UPDATE", "TOPOLOGY_SNAPSHOT", item.id, f"Topology view {item.name} updated")
    return {"id": item.id, "name": item.name, "layout_mode": item.layout_mode,
        "positions": item.positions, "viewport": item.viewport}


@router.post("/topology-layout/snapshots/{snapshot_id}/restore")
async def restore_topology_snapshot(snapshot_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(TopologySnapshot, snapshot_id)
    if not item: raise HTTPException(404, "Topology view not found")
    valid_devices = set((await db.execute(select(Device.id))).scalars().all())
    positions = [position for position in (item.positions or []) if position.get("device_id") in valid_devices]
    await db.execute(delete(TopologyPosition))
    db.add_all([TopologyPosition(device_id=position["device_id"], x=position["x"], y=position["y"], layout_mode=item.layout_mode) for position in positions])
    setting = await db.get(SystemSetting, "topology") or SystemSetting(key="topology"); setting.value = {"layout_mode": item.layout_mode}; db.add(setting)
    await _audit(db, "RESTORE", "TOPOLOGY_SNAPSHOT", item.id, f"Topology view {item.name} restored")
    return {"id": item.id, "name": item.name, "layout_mode": item.layout_mode,
        "positions": positions, "viewport": item.viewport or {}}


@router.delete("/topology-layout/snapshots/{snapshot_id}", status_code=204)
async def delete_topology_snapshot(snapshot_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(TopologySnapshot, snapshot_id)
    if not item: raise HTTPException(404, "Topology view not found")
    await _audit(db, "DELETE", "TOPOLOGY_SNAPSHOT", item.id, f"Topology view {item.name} deleted"); await db.delete(item)


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    item = await db.get(SystemSetting, "general")
    return item.value if item else SystemSettingsInput().model_dump()


@router.put("/settings")
async def save_settings(data: SystemSettingsInput, db: AsyncSession = Depends(get_db)):
    item = await db.get(SystemSetting, "general") or SystemSetting(key="general"); item.value = data.model_dump(); db.add(item); await _audit(db, "UPDATE", "SETTINGS", "general", "General settings updated")
    await db.commit()
    from app.services.monitoring_engine import monitoring_engine
    await monitoring_engine.load_configuration()
    return item.value


@router.get("/audit")
async def audit_logs(limit: int = 100, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)))).scalars().all()
    return [{"id": x.id, "action": x.action, "entity_type": x.entity_type, "entity_id": x.entity_id, "summary": x.summary, "created_at": x.created_at} for x in rows]


@router.get("/configuration/export")
async def export_configuration(db: AsyncSession = Depends(get_db)):
    devices = (await db.execute(select(Device))).scalars().all(); interfaces = (await db.execute(select(Interface))).scalars().all(); links = (await db.execute(select(Link))).scalars().all(); icons = (await db.execute(select(IconAsset))).scalars().all(); rules = (await db.execute(select(NotificationRule))).scalars().all(); settings = (await db.execute(select(SystemSetting))).scalars().all(); positions = (await db.execute(select(TopologyPosition))).scalars().all(); snapshots = (await db.execute(select(TopologySnapshot))).scalars().all(); redundancy = (await db.execute(select(RedundancyGroup))).scalars().all()
    def clean(obj, excluded=()):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in excluded}
    return {"format": "netmonitor-config", "version": 1, "exported_at": datetime.now(timezone.utc),
        "icons": [clean(x) for x in icons], "devices": [clean(x, ("snmp_community",)) for x in devices],
        "interfaces": [clean(x) for x in interfaces], "links": [clean(x) for x in links],
        "redundancy_groups": [clean(x) for x in redundancy], "notification_rules": [clean(x) for x in rules],
        "settings": [clean(x) for x in settings], "topology_positions": [clean(x) for x in positions],
        "topology_snapshots": [clean(x) for x in snapshots],
        "credentials_included": False}


@router.post("/configuration/import")
async def import_configuration(payload: dict, db: AsyncSession = Depends(get_db)):
    if payload.get("format") != "netmonitor-config" or payload.get("version") != 1: raise HTTPException(400, "Unsupported configuration backup")
    counts = {}; device_map = {}; interface_map = {}; link_map = {}; icon_map = {}

    def fields(model, raw, excluded=()):
        values = {k: v for k, v in raw.items() if k in model.__table__.columns.keys() and k not in {"id", "created_at", "updated_at", *excluded}}
        for key, value in list(values.items()):
            if value is not None and isinstance(model.__table__.columns[key].type, SQLDateTime) and isinstance(value, str):
                values[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return values

    for raw in payload.get("icons", []):
        existing = (await db.execute(select(IconAsset).where(IconAsset.key == raw.get("key")))).scalar_one_or_none()
        values = fields(IconAsset, raw)
        if existing:
            for key, value in values.items(): setattr(existing, key, value)
        else: existing = IconAsset(**values); db.add(existing); await db.flush()
        icon_map[raw.get("id")] = existing.id
    counts["icons"] = len(payload.get("icons", []))

    pending_device_refs = []
    for raw in payload.get("devices", []):
        existing = (await db.execute(select(Device).where(Device.name == raw.get("name")))).scalar_one_or_none()
        values = fields(Device, raw, ("gateway_device_id", "primary_link_id", "snmp_community"))
        values["icon_id"] = icon_map.get(raw.get("icon_id"))
        if existing:
            for key, value in values.items(): setattr(existing, key, value)
        else: existing = Device(**values); db.add(existing); await db.flush()
        device_map[raw.get("id")] = existing.id
        pending_device_refs.append((existing, raw.get("gateway_device_id"), raw.get("primary_link_id")))
    counts["devices"] = len(payload.get("devices", []))

    for raw in payload.get("interfaces", []):
        device_id = device_map.get(raw.get("device_id"))
        if not device_id: continue
        existing = (await db.execute(select(Interface).where(Interface.device_id == device_id,
            Interface.interface_name == raw.get("interface_name")))).scalar_one_or_none()
        values = fields(Interface, raw); values["device_id"] = device_id
        if existing:
            for key, value in values.items(): setattr(existing, key, value)
        else: existing = Interface(**values); db.add(existing); await db.flush()
        interface_map[raw.get("id")] = existing.id
    counts["interfaces"] = len(interface_map)

    for raw in payload.get("links", []):
        source_id, destination_id = device_map.get(raw.get("source_device_id")), device_map.get(raw.get("destination_device_id"))
        if not source_id or not destination_id: continue
        existing = (await db.execute(select(Link).where(Link.name == raw.get("name")))).scalar_one_or_none()
        values = fields(Link, raw); values.update({"source_device_id": source_id, "destination_device_id": destination_id,
            "source_interface_id": interface_map.get(raw.get("source_interface_id")), "destination_interface_id": interface_map.get(raw.get("destination_interface_id"))})
        if existing:
            for key, value in values.items(): setattr(existing, key, value)
        else: existing = Link(**values); db.add(existing); await db.flush()
        link_map[raw.get("id")] = existing.id
    counts["links"] = len(link_map)

    for device, gateway_id, primary_link_id in pending_device_refs:
        device.gateway_device_id = device_map.get(gateway_id); device.primary_link_id = link_map.get(primary_link_id)

    for raw in payload.get("redundancy_groups", []):
        existing = (await db.execute(select(RedundancyGroup).where(RedundancyGroup.name == raw.get("name")))).scalar_one_or_none()
        values = fields(RedundancyGroup, raw); values.update({"primary_link_id": link_map.get(raw.get("primary_link_id")),
            "secondary_link_id": link_map.get(raw.get("secondary_link_id")), "primary_device_id": device_map.get(raw.get("primary_device_id")),
            "secondary_device_id": device_map.get(raw.get("secondary_device_id"))})
        if existing:
            for key, value in values.items(): setattr(existing, key, value)
        else: db.add(RedundancyGroup(**values))
    counts["redundancy_groups"] = len(payload.get("redundancy_groups", []))

    for model, key, unique in [(NotificationRule, "notification_rules", "name"), (SystemSetting, "settings", "key")]:
        for raw in payload.get(key, []):
            values = fields(model, raw); marker = values.get(unique)
            existing = (await db.execute(select(model).where(getattr(model, unique) == marker))).scalar_one_or_none()
            if existing:
                for field, value in values.items(): setattr(existing, field, value)
            else: db.add(model(**values))
        counts[key] = len(payload.get(key, []))

    for raw in payload.get("topology_positions", []):
        device_id = device_map.get(raw.get("device_id"))
        if not device_id: continue
        existing = (await db.execute(select(TopologyPosition).where(TopologyPosition.device_id == device_id))).scalar_one_or_none()
        values = fields(TopologyPosition, raw); values["device_id"] = device_id
        if existing:
            for key, value in values.items(): setattr(existing, key, value)
        else: db.add(TopologyPosition(**values))
    counts["topology_positions"] = len(payload.get("topology_positions", []))
    for raw in payload.get("topology_snapshots", []):
        existing = (await db.execute(select(TopologySnapshot).where(TopologySnapshot.name == raw.get("name")))).scalar_one_or_none()
        remapped_positions = [{**position, "device_id": device_map.get(position.get("device_id"))}
            for position in raw.get("positions", []) if device_map.get(position.get("device_id"))]
        values = fields(TopologySnapshot, raw); values["positions"] = remapped_positions
        if existing:
            for key, value in values.items(): setattr(existing, key, value)
        else: db.add(TopologySnapshot(**values))
    counts["topology_snapshots"] = len(payload.get("topology_snapshots", []))
    await _audit(db, "IMPORT", "CONFIGURATION", None, f"Configuration imported: {counts}")
    return {"status": "imported", "counts": counts, "credentials_restored": False}
