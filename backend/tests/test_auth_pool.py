"""Authentication must not reserve a connection while an endpoint needs one."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import Response

import app.main as main
from app.models.platform import AuthSession, UserAccount
from app.services.auth_service import token_digest


@pytest_asyncio.fixture
async def auth_pool(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}",
                                 pool_size=1, max_overflow=0, pool_timeout=5)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(UserAccount.__table__.create)
        await conn.run_sync(AuthSession.__table__.create)
    now = datetime.now(timezone.utc)
    async with factory() as db:
        user = UserAccount(username="pool-test", display_name="Pool Test",
                           password_hash="unused", role="ADMINISTRATOR", enabled=True)
        db.add(user)
        await db.flush()
        db.add(AuthSession(user_id=user.id, token_hash=token_digest("test-session"),
                           expires_at=now + timedelta(hours=1), last_seen_at=now - timedelta(minutes=2)))
        await db.commit()
    monkeypatch.setattr(main, "async_session_factory", factory)
    monkeypatch.setattr(main, "settings", SimpleNamespace(AUTH_DISABLED=False))
    try:
        yield factory, engine
    finally:
        await engine.dispose()


def request(path="/api/devices", method="GET", token="test-session"):
    return Request({"type": "http", "method": method, "path": path,
                    "headers": [(b"authorization", f"Bearer {token}".encode())]})


@pytest.mark.asyncio
async def test_concurrent_requests_release_auth_connection_before_endpoint(auth_pool):
    factory, engine = auth_pool

    async def endpoint(req):
        assert req.state.user.username == "pool-test"
        async with factory() as db:
            assert (await db.execute(select(UserAccount.id))).scalar_one()
            await asyncio.sleep(0.001)
        return Response(status_code=200)

    responses = await asyncio.gather(*(main.authentication(request(), endpoint) for _ in range(20)))
    assert all(response.status_code == 200 for response in responses)
    assert engine.pool.checkedout() == 0


@pytest.mark.asyncio
async def test_account_mutation_still_persists(auth_pool):
    factory, _ = auth_pool

    async def endpoint(req):
        req.state.user.password_hash = "changed-test-hash"
        return Response(status_code=204)

    result = await main.authentication(request("/api/auth/change-password", "POST"), endpoint)
    assert result.status_code == 204
    async with factory() as db:
        assert (await db.execute(select(UserAccount.password_hash))).scalar_one() == "changed-test-hash"


@pytest.mark.asyncio
async def test_logout_revokes_session(auth_pool):
    factory, _ = auth_pool

    async def endpoint(req):
        req.state.logout_requested = True
        return Response(status_code=204)

    assert (await main.authentication(request("/api/auth/logout", "POST"), endpoint)).status_code == 204
    async with factory() as db:
        assert (await db.execute(select(AuthSession.id))).first() is None


@pytest.mark.asyncio
async def test_exhausted_pool_returns_retryable_error_not_invalid_credentials(auth_pool):
    factory, _ = auth_pool
    async with factory() as held:
        await held.execute(select(UserAccount.id))
        async def endpoint(req):
            pytest.fail("Saturated authentication must not execute endpoint")
        response = await main.authentication(request(), endpoint)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert b"DATABASE_BUSY" in response.body


@pytest.mark.asyncio
async def test_failed_account_commit_does_not_report_success(auth_pool):
    async def endpoint(req):
        req.state.user.password_hash = "not-saved"
        async def fail_commit():
            raise OperationalError("sensitive statement", {}, Exception("sensitive detail"))
        req.state.auth_db.commit = fail_commit
        return Response(status_code=204)
    response = await main.authentication(request("/api/auth/change-password", "POST"), endpoint)
    assert response.status_code == 503
    assert b"sensitive" not in response.body
