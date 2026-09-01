import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

BOOTSTRAP_FILE = Path(__file__).resolve().parents[1] / ".active-database"


def _cipher(secret_key: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest()))


def load_active_database(default_url: str, secret_key: str) -> tuple[str, dict | None]:
    if not BOOTSTRAP_FILE.exists():
        return default_url, None
    try:
        payload = json.loads(BOOTSTRAP_FILE.read_text(encoding="utf-8"))
        url = _cipher(secret_key).decrypt(payload["encrypted_url"].encode("ascii")).decode("utf-8")
        metadata = {key: payload.get(key) for key in ("connection_id", "name", "database_type", "activated_at")}
        metadata["rollback_available"] = bool(payload.get("encrypted_previous_url"))
        return url, metadata
    except (OSError, ValueError, KeyError, InvalidToken, json.JSONDecodeError):
        return default_url, None


def save_active_database(url: str, secret_key: str, metadata: dict, previous_url: str | None = None,
                         previous_metadata: dict | None = None) -> None:
    cipher = _cipher(secret_key)
    payload = {**metadata, "encrypted_url": cipher.encrypt(url.encode("utf-8")).decode("ascii")}
    if previous_url:
        payload["encrypted_previous_url"] = cipher.encrypt(previous_url.encode("utf-8")).decode("ascii")
        payload["previous_name"] = (previous_metadata or {}).get("name", "Banco anterior")
        payload["previous_database_type"] = (previous_metadata or {}).get("database_type", "DEFAULT")
    temporary = BOOTSTRAP_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, BOOTSTRAP_FILE)


def get_previous_database(secret_key: str) -> tuple[str, dict] | None:
    try:
        payload = json.loads(BOOTSTRAP_FILE.read_text(encoding="utf-8"))
        encrypted = payload.get("encrypted_previous_url")
        if not encrypted: return None
        url = _cipher(secret_key).decrypt(encrypted.encode("ascii")).decode("utf-8")
        return url, {"name": payload.get("previous_name", "Banco anterior"),
            "database_type": payload.get("previous_database_type", "DEFAULT")}
    except (OSError, ValueError, KeyError, InvalidToken, json.JSONDecodeError):
        return None


def rollback_active_database(secret_key: str) -> dict:
    previous = get_previous_database(secret_key)
    if not previous: raise ValueError("No previous database is available")
    current_url, current_metadata = load_active_database("", secret_key)
    previous_url, previous_metadata = previous
    activated_at = datetime.now(timezone.utc).isoformat()
    save_active_database(previous_url, secret_key, {**previous_metadata, "connection_id": None,
        "activated_at": activated_at}, previous_url=current_url, previous_metadata=current_metadata or {})
    return {"status": "READY", "restart_required": True, "name": previous_metadata["name"],
        "database_type": previous_metadata["database_type"], "activated_at": activated_at}
