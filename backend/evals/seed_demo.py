"""Explicitly prepare local demo accounts and the three curated fictional scenarios."""

import asyncio
import json
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from evals.demo_credentials import get_demo_credentials_pair
from scripts.import_market_scenarios import seed_scenarios, validate_local_url

BASE = "http://127.0.0.1:8000/api/v1"


def data(response):
    response.raise_for_status()
    return response.json()["data"]


async def seed_jobs(owner_id):
    if settings.app_env != "development":
        raise RuntimeError("Demo seed is restricted to development")
    validate_local_url(settings.database_url)
    engine = create_async_engine(settings.database_url, hide_parameters=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await seed_scenarios(session, owner_id)
    finally:
        await engine.dispose()


def seed():
    accounts = get_demo_credentials_pair()
    for role, name in (("student", "演示学生"), ("enterprise", "演示企业")):
        with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
            credentials = accounts[role]
            registered = client.post(
                "/auth/register", json={**credentials, "displayName": name, "role": role}
            )
            if registered.status_code != 409:
                data(registered)
            login = client.post("/auth/login", json=credentials)
            if login.status_code == 401:
                raise RuntimeError(
                    "Demo login failed; changing local credentials does not reset an existing "
                    "account password. Restore the original local credentials, or explicitly "
                    "configure two new demo email addresses. Existing accounts are left unchanged."
                )
            user = data(login)["user"]
            if user["role"] != role:
                raise RuntimeError("Existing demo account has a different role; left unchanged")
            print(f"Verified login: {credentials['email']} ({role})")
            if role == "enterprise":
                result = asyncio.run(seed_jobs(UUID(user["id"])))
                print(json.dumps({"curatedJobs": result}, ensure_ascii=False))
            data(client.post("/auth/logout"))


if __name__ == "__main__":
    seed()
