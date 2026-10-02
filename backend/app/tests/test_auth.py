"""Authentication coverage: token primitives, service rules and HTTP flow.

Fills the previous testing gap around login/register/refresh: rotation and
revocation of refresh tokens, role restrictions on public registration and
HttpOnly cookie behavior at the API layer. Everything runs on temporary SQLite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import security
from app.core.config import settings
from app.core.database import Base, get_session
from app.core.exceptions import AppError
from app.main import create_app
from app.models.enums import UserRole
from app.models.identity import StudentProfile
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth import AuthService

PASSWORD = "auth-test-password-123"


@pytest.fixture
async def auth_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection, _record):
        connection.create_function(
            "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
        )
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[t for t in Base.metadata.sorted_tables if t.name != "knowledge_chunks"],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = session_override
    try:
        yield app, factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.fixture
async def client(auth_db):
    app, _factory = auth_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


async def _register_request(role: UserRole = UserRole.STUDENT, email: str | None = None):
    return RegisterRequest(
        email=email or f"auth-{datetime.now(UTC).timestamp()}@example.com",
        password=PASSWORD,
        display_name="鉴权测试用户",
        role=role,
    )


def _expired_now(*_args, **_kwargs):
    return datetime.now(UTC) - timedelta(days=30)


# ---------- token 原语 ----------


def test_access_and_refresh_tokens_roundtrip():
    subject = security.uuid4()
    encoded, jti, expires = security.create_token(subject, "student", "refresh")
    payload = security.decode_token(encoded, "refresh")
    assert payload["sub"] == str(subject)
    assert payload["jti"] == jti
    assert payload["type"] == "refresh"
    assert payload["role"] == "student"
    assert expires > datetime.now(UTC)


def test_decode_token_rejects_wrong_type():
    encoded, _jti, _expires = security.create_token(security.uuid4(), "student", "access")
    with pytest.raises(AppError) as error:
        security.decode_token(encoded, "refresh")
    assert error.value.status_code == 401
    assert error.value.code == 4011


def test_decode_token_rejects_foreign_signature():
    encoded, _jti, _expires = security.create_token(security.uuid4(), "student", "access")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "jwt_secret", "another-secret-with-32-chars-minimum!")
        with pytest.raises(AppError):
            security.decode_token(encoded, "access")


def test_decode_token_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(security, "datetime", type("FakeDateTime", (), {"now": staticmethod(_expired_now)}))
    encoded, _jti, _expires = security.create_token(security.uuid4(), "student", "access")
    monkeypatch.undo()
    with pytest.raises(AppError) as error:
        security.decode_token(encoded, "access")
    assert error.value.code == 4010


def test_token_digest_is_sha256_hex():
    assert security.token_digest("abc") == security.token_digest("abc")
    assert security.token_digest("abc") != security.token_digest("abd")
    assert len(security.token_digest("abc")) == 64


# ---------- 服务层规则 ----------


async def test_register_creates_student_profile_and_hashes_password(auth_db):
    _app, factory = auth_db
    async with factory() as session:
        tokens = await AuthService(session).register(await _register_request())
        assert tokens.user.role is UserRole.STUDENT
        assert tokens.user.password_hash != PASSWORD
        assert security.verify_password(PASSWORD, tokens.user.password_hash)
        profile_id = await session.scalar(select(StudentProfile.id))
        assert profile_id, "student registration must create a profile row"


async def test_register_rejects_duplicate_email_and_admin_role(auth_db):
    _app, factory = auth_db
    async with factory() as session:
        service = AuthService(session)
        email = "duplicate@example.com"
        await service.register(await _register_request(email=email))
        with pytest.raises(AppError) as duplicate:
            await service.register(await _register_request(email=email))
        assert duplicate.value.status_code == 409
        with pytest.raises(AppError) as forbidden:
            await service.register(await _register_request(role=UserRole.ADMIN))
        assert forbidden.value.status_code == 403


async def test_login_rejects_wrong_password_and_inactive_account(auth_db):
    _app, factory = auth_db
    request = LoginRequest(
        email="login-flow@example.com", password=PASSWORD
    )
    async with factory() as session:
        tokens = await AuthService(session).register(
            await _register_request(email="login-flow@example.com")
        )
        user = tokens.user
        assert (await AuthService(session).login(request)).user.id == user.id
        with pytest.raises(AppError) as wrong_password:
            await AuthService(session).login(
                LoginRequest(email="login-flow@example.com", password="wrong-password-1")
            )
        assert wrong_password.value.status_code == 401
        user.is_active = False
        await session.commit()
        with pytest.raises(AppError) as inactive:
            await AuthService(session).login(request)
        assert inactive.value.status_code == 403


async def test_refresh_rotates_and_revokes_previous_token(auth_db):
    _app, factory = auth_db
    async with factory() as session:
        issued = await AuthService(session).register(
            await _register_request(email="rotation@example.com")
        )
        first_refresh = issued.refresh_token
        rotated = await AuthService(session).refresh(first_refresh)
        assert rotated.refresh_token != first_refresh
        # 旧 refresh 已撤销：再次使用必须失败。
        with pytest.raises(AppError) as reused:
            await AuthService(session).refresh(first_refresh)
        assert reused.value.status_code == 401
        # 新 refresh 仍可继续轮换。
        again = await AuthService(session).refresh(rotated.refresh_token)
        assert again.refresh_token != rotated.refresh_token


async def test_refresh_rejects_unknown_and_revoked_states(auth_db):
    _app, factory = auth_db
    async with factory() as session:
        service = AuthService(session)
        with pytest.raises(AppError) as unknown:
            await service.refresh(
                security.create_token(security.uuid4(), "student", "refresh")[0]
            )
        assert unknown.value.status_code == 401
        issued = await service.register(await _register_request(email="revoke@example.com"))
        await service.revoke(issued.refresh_token)
        with pytest.raises(AppError):
            await service.refresh(issued.refresh_token)


async def test_revoke_ignores_missing_or_invalid_token(auth_db):
    _app, factory = auth_db
    async with factory() as session:
        service = AuthService(session)
        await service.revoke(None)
        await service.revoke("not-a-jwt")
        issued = await service.register(await _register_request(email="still-valid@example.com"))
        rotated = await service.refresh(issued.refresh_token)
        assert rotated.refresh_token


# ---------- API 层与 Cookie ----------


async def test_register_login_and_refresh_over_http_with_cookies(client):
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "cookie-flow@example.com",
            "password": PASSWORD,
            "displayName": "Cookie 用户",
            "role": "student",
        },
    )
    assert register_response.status_code == 201, register_response.text
    set_cookie = register_response.headers["set-cookie"]
    assert "careerproof_access=" in set_cookie
    assert "careerproof_refresh=" in set_cookie
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()

    me_response = await client.get("/api/v1/users/me")
    assert me_response.status_code == 200
    assert me_response.json()["data"]["email"] == "cookie-flow@example.com"

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookie-flow@example.com", "password": PASSWORD},
    )
    assert login_response.status_code == 200
    assert login_response.cookies.get("careerproof_refresh")

    refresh_response = await client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    assert client.cookies.get("careerproof_refresh")


async def test_refresh_without_cookie_is_rejected(client):
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


async def test_logout_revokes_refresh_and_clears_cookies(client, auth_db):
    _app, factory = auth_db
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout@example.com",
            "password": PASSWORD,
            "displayName": "登出用户",
            "role": "student",
        },
    )
    refresh_cookie = client.cookies.get("careerproof_refresh")
    assert refresh_cookie

    logout_response = await client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200
    assert not client.cookies.get("careerproof_refresh")

    async with factory() as session:
        from app.models.identity import RefreshToken

        stored = list(await session.scalars(select(RefreshToken)))
        assert stored and all(item.revoked_at is not None for item in stored)

    reuse = await client.post("/api/v1/auth/refresh")
    assert reuse.status_code == 401


async def test_public_registration_rejects_admin_role(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin-attempt@example.com",
            "password": PASSWORD,
            "displayName": "越权尝试",
            "role": "admin",
        },
    )
    assert response.status_code == 403


async def test_weak_password_rejected_by_validation(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "short",
            "displayName": "弱口令",
            "role": "student",
        },
    )
    assert response.status_code == 422


async def test_http_error_shape_is_consistent(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": PASSWORD},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == 4012
    assert "message" in body
