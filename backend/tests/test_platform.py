import asyncio
import os
import shutil
import tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="netmonitor-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TEST_DIR / 'source.db').as_posix()}"
os.environ["SECRET_KEY"] = "automated-test-secret"

import pytest
from fastapi.testclient import TestClient

import app.db_bootstrap as bootstrap
from app.database import engine
from app.main import app


@pytest.fixture(scope="session")
def client():
    bootstrap.BOOTSTRAP_FILE = TEST_DIR / ".active-database"
    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(engine.dispose())
    shutil.rmtree(TEST_DIR, ignore_errors=True)


def test_secrets_are_never_returned(client):
    response = client.put("/api/platform/notifications/TELEGRAM", json={
        "provider": "TELEGRAM", "name": "Telegram", "enabled": False,
        "config": {"chat_id": "123"}, "secrets": {"bot_token": "never-return-this"},
    })
    assert response.status_code == 200
    assert "never-return-this" not in response.text
    assert response.json()["secrets_configured"] == ["bot_token"]


def test_read_only_data_source(client):
    connection = client.post("/api/platform/databases", json={
        "name": "SQLite test", "database_type": "SQLITE", "database_name": ":memory:",
    })
    assert connection.status_code == 201
    source = client.post("/api/platform/data-sources", json={
        "connection_id": connection.json()["id"], "name": "Health", "query_text": "SELECT 1 AS status",
    })
    assert source.status_code == 201
    result = client.post(f"/api/platform/data-sources/{source.json()['id']}/test")
    assert result.json()["rows"] == [{"status": 1}]
    unsafe = client.post("/api/platform/data-sources", json={
        "connection_id": connection.json()["id"], "name": "Unsafe", "query_text": "DELETE FROM devices",
    })
    assert unsafe.status_code == 422


def test_database_default_ports(client):
    mysql = client.post("/api/platform/databases", json={
        "name": "MySQL defaults", "database_type": "MYSQL", "host": "db.internal",
        "database_name": "network_monitor",
    })
    assert mysql.status_code == 201
    assert mysql.json()["port"] == 3306


def test_topology_and_backup_round_trip(client):
    gateway = client.post("/api/devices", json={"name": "Gateway test", "device_type": "ROUTER", "location": "Lab"})
    child = client.post("/api/devices", json={"name": "Child test", "device_type": "SWITCH", "location": "Lab", "gateway_device_id": gateway.json()["id"]})
    assert gateway.status_code == child.status_code == 201
    layout = client.put("/api/platform/topology-layout", json={"layout_mode": "free", "positions": [
        {"device_id": gateway.json()["id"], "x": 25, "y": 40},
        {"device_id": child.json()["id"], "x": 25, "y": 240},
    ]})
    assert layout.status_code == 200
    snapshot = client.post("/api/platform/topology-layout/snapshots", json={
        "name": "Layout seguro", "layout_mode": "free",
        "positions": [{"device_id": gateway.json()["id"], "x": 25, "y": 40},
                      {"device_id": child.json()["id"], "x": 25, "y": 240}],
        "viewport": {"x": 10, "y": 20, "zoom": 0.8},
    })
    assert snapshot.status_code == 201
    client.put("/api/platform/topology-layout", json={"layout_mode": "free", "positions": []})
    restored_view = client.post(f"/api/platform/topology-layout/snapshots/{snapshot.json()['id']}/restore")
    assert restored_view.status_code == 200
    assert len(restored_view.json()["positions"]) == 2
    backup = client.get("/api/platform/configuration/export")
    assert backup.status_code == 200
    assert backup.json()["credentials_included"] is False
    restored = client.post("/api/platform/configuration/import", json=backup.json())
    assert restored.status_code == 200
    assert restored.json()["counts"]["links"] >= 1
    assert restored.json()["counts"]["topology_snapshots"] == 1


def test_primary_database_migration(client):
    target = TEST_DIR / "preferred.db"
    connection = client.post("/api/platform/databases", json={
        "name": "Preferred database", "database_type": "SQLITE", "database_name": str(target), "enabled": True,
    })
    activated = client.post(f"/api/platform/databases/{connection.json()['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["restart_required"] is True
    assert activated.json()["migrated_records"] > 0
    assert bootstrap.BOOTSTRAP_FILE.exists()
    assert str(target) not in bootstrap.BOOTSTRAP_FILE.read_text(encoding="utf-8")
