import base64
import hashlib
import json
import os
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
        return url, {key: payload.get(key) for key in ("connection_id", "name", "database_type", "activated_at")}
    except (OSError, ValueError, KeyError, InvalidToken, json.JSONDecodeError):
        return default_url, None


def save_active_database(url: str, secret_key: str, metadata: dict) -> None:
    payload = {**metadata, "encrypted_url": _cipher(secret_key).encrypt(url.encode("utf-8")).decode("ascii")}
    temporary = BOOTSTRAP_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, BOOTSTRAP_FILE)
