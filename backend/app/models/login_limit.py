from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LoginLimit(Base):
    __tablename__ = "login_limits"
    __table_args__ = (
        CheckConstraint("attempts > 0", name="ck_login_limits_positive_attempts"),
        CheckConstraint("scope IN ('source', 'pair')", name="ck_login_limits_scope"),
        Index("ix_login_limits_expires_at", "expires_at"),
    )

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(BigInteger)
