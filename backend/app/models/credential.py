from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class IGLoginCredential(Base):
    __tablename__ = "ig_login_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_enc: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet encrypted
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), unique=True
    )
    ig_user_id: Mapped[str | None] = mapped_column(String(50))
    page_access_token_enc: Mapped[str | None] = mapped_column(Text)  # Fernet encrypted
    user_access_token_enc: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column()
    saved_at: Mapped[datetime] = mapped_column(default=_utcnow)
