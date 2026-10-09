"""Explicit audited activation only inside already verified test-owned databases."""

from uuid import uuid4

from sqlalchemy import text

from app.models.enums import UserRole
from app.models.identity import User
from app.services.ai_budget import SharedBudgetService


async def activate_owned_test_budget(factory, *, schema=None):
    async with factory() as session:
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            if not schema or await session.scalar(text("SELECT current_schema()")) != schema:
                raise AssertionError("Budget fixture requires the exact owned schema")
            for name in (
                "users",
                "analysis_tasks",
                "ai_request_attempts",
                "ai_daily_budgets",
                "ai_budget_reservations",
                "ai_budget_adjustments",
                "ai_budget_cutover",
            ):
                assert (
                    await session.scalar(
                        text(
                            "SELECT n.nspname FROM pg_class c "
                            "JOIN pg_namespace n ON n.oid=c.relnamespace "
                            "WHERE c.oid=to_regclass(:name)",
                        ),
                        {"name": name},
                    )
                    == schema
                )
        elif dialect != "sqlite":
            raise AssertionError("Unsupported test fixture database")
        actor = User(
            id=uuid4(),
            email=f"budget-admin-{uuid4()}@synthetic.invalid",
            password_hash="synthetic",
            display_name="isolated test budget administrator",
            role=UserRole.ADMIN,
        )
        session.add(actor)
        await session.flush()
        await SharedBudgetService().activate(
            session,
            actor_id=actor.id,
            reason="audited empty inventory in isolated test database",
        )
        await session.commit()
        return actor.id
