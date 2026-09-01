import asyncio
import base64
import json
import smtplib
import sqlite3
from datetime import datetime, timezone
from email.message import EmailMessage

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import DateTime as SQLDateTime, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database import active_database_metadata, active_database_url, engine
from app.models.device import Device
from app.models.interface import Interface
from app.models.link import Link
from app.models.platform import (AuditLog, DatabaseConnection, DatabaseDataSource, IconAsset,
    NotificationIntegration, NotificationRule, SystemSetting, TopologyPosition)
from app.models.redundancy_group import RedundancyGroup
from app.schemas.platform import (DatabaseConnectionInput, DatabaseConnectionRead, DatabaseDataSourceInput, DatabaseDataSourceRead,
    IconRead, NotificationIntegrationInput, NotificationIntegrationRead,
    NotificationRuleInput, NotificationRuleRead, SystemSettingsInput, TopologyLayoutInput)
from app.security import decrypt_secret, encrypt_secret
from app.services.database_switcher import migrate_and_activate

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
    if active_database_metadata:
        return {"mode": "CONFIGURED", **active_database_metadata, "restart_pending": False}
    return {"mode": "DEFAULT", "connection_id": None, "name": "SQLite local",
        "database_type": "SQLITE" if active_database_url.startswith("sqlite") else "ENVIRONMENT",
        "activated_at": None, "restart_pending": False}


@router.post("/databases/{item_id}/activate")
async def activate_database(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(DatabaseConnection, item_id)
    if not item: raise HTTPException(404, "Database connection not found")
    if not item.enabled: raise HTTPException(400, "Enable the connection before making it primary")
    try:
        await _test_database(item)
        await _audit(db, "MIGRATION_STARTED", "DATABASE", item.id, f"Migration to {item.name} started")
        await db.commit()
        result = await migrate_and_activate(engine, item)
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
    if item.database_type == "SQLITE":
        await asyncio.to_thread(lambda: sqlite3.connect(item.database_name, timeout=3).close())
        return
    if item.database_type == "POSTGRESQL":
        import asyncpg
        connection = await asyncio.wait_for(asyncpg.connect(host=item.host, port=item.port or 5432,
            database=item.database_name, user=item.username, password=decrypt_secret(item.encrypted_password),
            ssl="require" if item.ssl_enabled else None, timeout=5), timeout=6)
        try: await connection.execute("SELECT 1")
        finally: await connection.close()
        return
    if not item.host or not item.port: raise ValueError("Host and port are required")
    reader, writer = await asyncio.wait_for(asyncio.open_connection(item.host, item.port), timeout=5)
    writer.close(); await writer.wait_closed()


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
    query = f"SELECT * FROM ({source.query_text}) AS netmonitor_source LIMIT 100"
    if connection.database_type == "SQLITE":
        def execute():
            db = sqlite3.connect(connection.database_name, timeout=5); db.row_factory = sqlite3.Row
            try: return [dict(row) for row in db.execute(query, source.parameters or {}).fetchall()]
            finally: db.close()
        return await asyncio.to_thread(execute)
    if connection.database_type == "POSTGRESQL":
        import asyncpg
        db = await asyncpg.connect(host=connection.host, port=connection.port or 5432, database=connection.database_name,
            user=connection.username, password=decrypt_secret(connection.encrypted_password), ssl="require" if connection.ssl_enabled else None, timeout=5)
        try: return [dict(row) for row in await db.fetch(query, *(source.parameters or {}).values())]
        finally: await db.close()
    raise ValueError("Query execution driver is not installed for this database type")


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
    item.name, item.enabled, item.public_config = data.name, data.enabled, data.config
    item.encrypted_secrets = encrypt_secret(json.dumps(existing)); await db.flush(); await _audit(db, "UPSERT", "NOTIFICATION", item.id, f"{provider} integration saved")
    return _integration_read(item)


async def _send_notification_test(item: NotificationIntegration):
    cfg = item.public_config or {}; sec = json.loads(decrypt_secret(item.encrypted_secrets) or "{}")
    if item.provider == "TELEGRAM":
        token, chat = sec.get("bot_token"), cfg.get("chat_id")
        if not token or not chat: raise ValueError("Bot token and Chat ID are required")
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": "NetMonitor: teste de integração concluído."}); response.raise_for_status()
    elif item.provider == "WHATSAPP":
        url, token = cfg.get("api_url"), sec.get("api_token")
        if not url or not token: raise ValueError("API URL and token are required")
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json={"sender": cfg.get("sender_id"), "recipient": cfg.get("recipient"), "message": "NetMonitor: teste de integração concluído."}); response.raise_for_status()
    elif item.provider == "EMAIL":
        host, recipients = cfg.get("smtp_server"), cfg.get("recipients", [])
        if not host or not recipients: raise ValueError("SMTP server and recipients are required")
        msg = EmailMessage(); msg["Subject"] = "NetMonitor - Teste"; msg["From"] = cfg.get("from_address"); msg["To"] = ", ".join(recipients); msg.set_content("Integração de email configurada com sucesso.")
        def send():
            smtp_cls = smtplib.SMTP_SSL if cfg.get("ssl") else smtplib.SMTP
            with smtp_cls(host, int(cfg.get("smtp_port", 587)), timeout=8) as smtp:
                if cfg.get("tls") and not cfg.get("ssl"): smtp.starttls()
                if cfg.get("username"): smtp.login(cfg["username"], sec.get("password", ""))
                smtp.send_message(msg)
        await asyncio.to_thread(send)


@router.post("/notifications/{provider}/test")
async def test_notification(provider: str, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(NotificationIntegration).where(NotificationIntegration.provider == provider.upper()))).scalar_one_or_none()
    if not item: raise HTTPException(404, "Notification integration not found")
    try:
        await _send_notification_test(item); item.last_status = "SUCCESS"; item.last_error = None
    except Exception:
        item.last_status = "FAILED"; item.last_error = "Provider rejected the test or could not be reached. Verify configuration and network access."
    item.last_tested_at = datetime.now(timezone.utc); await _audit(db, "TEST", "NOTIFICATION", item.id, f"{item.provider} test: {item.last_status}")
    return {"status": item.last_status, "message": item.last_error or "Test notification sent."}


@router.get("/notification-rules", response_model=list[NotificationRuleRead])
async def list_rules(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(NotificationRule).order_by(NotificationRule.name))).scalars().all()


@router.post("/notification-rules", response_model=NotificationRuleRead, status_code=201)
async def create_rule(data: NotificationRuleInput, db: AsyncSession = Depends(get_db)):
    item = NotificationRule(**data.model_dump()); db.add(item); await db.flush(); await _audit(db, "CREATE", "NOTIFICATION_RULE", item.id, f"Rule {item.name} created"); return item


@router.put("/notification-rules/{item_id}", response_model=NotificationRuleRead)
async def update_rule(item_id: int, data: NotificationRuleInput, db: AsyncSession = Depends(get_db)):
    item = await db.get(NotificationRule, item_id)
    if not item: raise HTTPException(404, "Notification rule not found")
    for k, v in data.model_dump().items(): setattr(item, k, v)
    await _audit(db, "UPDATE", "NOTIFICATION_RULE", item.id, f"Rule {item.name} updated"); return item


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
    devices = (await db.execute(select(Device))).scalars().all(); interfaces = (await db.execute(select(Interface))).scalars().all(); links = (await db.execute(select(Link))).scalars().all(); icons = (await db.execute(select(IconAsset))).scalars().all(); rules = (await db.execute(select(NotificationRule))).scalars().all(); settings = (await db.execute(select(SystemSetting))).scalars().all(); positions = (await db.execute(select(TopologyPosition))).scalars().all(); redundancy = (await db.execute(select(RedundancyGroup))).scalars().all()
    def clean(obj, excluded=()):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in excluded}
    return {"format": "netmonitor-config", "version": 1, "exported_at": datetime.now(timezone.utc),
        "icons": [clean(x) for x in icons], "devices": [clean(x, ("snmp_community",)) for x in devices],
        "interfaces": [clean(x) for x in interfaces], "links": [clean(x) for x in links],
        "redundancy_groups": [clean(x) for x in redundancy], "notification_rules": [clean(x) for x in rules],
        "settings": [clean(x) for x in settings], "topology_positions": [clean(x) for x in positions],
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
    await _audit(db, "IMPORT", "CONFIGURATION", None, f"Configuration imported: {counts}")
    return {"status": "imported", "counts": counts, "credentials_restored": False}
