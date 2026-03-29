"""User and Network models for multi-tenant auth."""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="member")  # "owner" or "member"
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    network_memberships: Mapped[list["UserNetwork"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Network(Base):
    __tablename__ = "networks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    ig_app_id: Mapped[str | None] = mapped_column(String(100))
    ig_app_secret_enc: Mapped[str | None] = mapped_column(Text)  # Fernet encrypted
    ig_redirect_uri: Mapped[str | None] = mapped_column(String(500))
    public_url: Mapped[str | None] = mapped_column(String(500))
    api_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    members: Mapped[list["UserNetwork"]] = relationship(
        back_populates="network", cascade="all, delete-orphan"
    )


class UserNetwork(Base):
    __tablename__ = "user_networks"
    __table_args__ = (UniqueConstraint("user_id", "network_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    network_id: Mapped[int] = mapped_column(ForeignKey("networks.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default="member")  # "admin" or "member"

    user: Mapped["User"] = relationship(back_populates="network_memberships")
    network: Mapped["Network"] = relationship(back_populates="members")
