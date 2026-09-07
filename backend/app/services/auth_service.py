import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.models.platform import AuthSession, UserAccount

ROLES = {"VIEWER", "OPERATOR", "ADMINISTRATOR"}


def hash_password(password: str) -> str:
    settings = get_settings(); salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=settings.PASSWORD_SCRYPT_N, r=settings.PASSWORD_SCRYPT_R, p=settings.PASSWORD_SCRYPT_P)
    return "$".join(("scrypt", str(settings.PASSWORD_SCRYPT_N), str(settings.PASSWORD_SCRYPT_R), str(settings.PASSWORD_SCRYPT_P), base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt": return False
        digest = hashlib.scrypt(password.encode(), salt=base64.urlsafe_b64decode(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(digest, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError): return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(db, user: UserAccount) -> tuple[str, AuthSession]:
    settings = get_settings(); token = secrets.token_urlsafe(48); now = datetime.now(timezone.utc)
    session = AuthSession(user_id=user.id, token_hash=token_digest(token), expires_at=now + timedelta(minutes=settings.AUTH_SESSION_MINUTES), last_seen_at=now)
    db.add(session); await db.flush(); return token, session


async def authenticate_token(db, token: str) -> tuple[UserAccount, AuthSession] | None:
    result = await db.execute(select(AuthSession, UserAccount).join(UserAccount, UserAccount.id == AuthSession.user_id).where(AuthSession.token_hash == token_digest(token), UserAccount.enabled == True))
    row = result.first()
    if not row: return None
    session, user = row; now = datetime.now(timezone.utc); expiry = session.expires_at.replace(tzinfo=timezone.utc) if session.expires_at.tzinfo is None else session.expires_at
    if expiry <= now: await db.delete(session); await db.commit(); return None
    session.last_seen_at = now
    return user, session
