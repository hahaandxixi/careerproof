"""Read-only verification of preserved synthetic withdrawal and exact notice targets."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import AppError
from app.models.identity import User
from app.models.notification import Notification
from app.models.recruitment import Application, ApplicationEvent
from app.services.notifications import NotificationService


async def main():
    run = "audit-20261005"
    url = make_url(os.environ["CAREERPROOF_AUDIT_DATABASE_URL"])
    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "127.0.0.1" and url.port == 5432
    assert url.database == f"cp_e2e_{run}"
    root = Path(__file__).resolve().parents[3]
    fixture = json.loads((root / "backend/.tmp/e2e" / f"{run}.json").read_text(encoding="utf-8-sig"))
    assert fixture["runId"] == run
    engine = create_async_engine(url)
    results = {"runId": run, "transactionReadOnly": True, "applications": {}, "notifications": []}
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            assert await session.scalar(text("SELECT current_database()")) == f"cp_e2e_{run}"
            assert await session.scalar(text("SHOW transaction_read_only")) == "on"
            user = await session.get(User, UUID(fixture["accounts"]["enterprise"]["userId"]))
            assert user is not None
            for slot, record in fixture["applications"].items():
                app = await session.get(Application, UUID(record["id"]))
                digest = hashlib.sha256(json.dumps(app.report_snapshot, sort_keys=True, ensure_ascii=False,
                                                   separators=(",", ":")).encode("utf-8")).hexdigest()
                assert digest == record["snapshotSha256"]
                assert (app.status == "withdrawn") == (slot == "A")
                results["applications"][slot] = {"id": str(app.id), "status": app.status,
                                                 "snapshotSha256": digest, "matchesOriginal": True}
                rows = (await session.execute(select(Notification, ApplicationEvent)
                    .join(ApplicationEvent, Notification.event_id == ApplicationEvent.id)
                    .where(Notification.recipient_id == user.id, ApplicationEvent.application_id == app.id))).all()
                assert rows, f"Missing synthetic notices for {slot}"
                for notice, event in rows:
                    try:
                        target = await NotificationService(session).target(notice.id, user)
                        assert slot != "A"
                        assert target["href"].endswith(f"#application-{app.id}")
                        outcome = {"status": 200, "targetMatchesApplication": True}
                    except AppError as error:
                        assert slot == "A" and error.status_code == 404
                        outcome = {"status": 404, "targetMatchesApplication": False}
                    results["notifications"].append({"notificationId": str(notice.id),
                        "eventId": str(event.id), "eventType": event.event_type,
                        "applicationId": str(app.id), "slot": slot, **outcome})
            await session.rollback()
        results["writes"] = 0
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
