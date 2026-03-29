from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Niche(Base):
    __tablename__ = "niches"
    __table_args__ = (UniqueConstraint("network_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    network_id: Mapped[int | None] = mapped_column(ForeignKey("networks.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    accounts: Mapped[list["NicheAccount"]] = relationship(
        back_populates="niche", cascade="all, delete-orphan"
    )


class NicheAccount(Base):
    __tablename__ = "niche_accounts"
    __table_args__ = (UniqueConstraint("niche_id", "username", "platform"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id", ondelete="CASCADE"))
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="instagram")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    niche: Mapped["Niche"] = relationship(back_populates="accounts")
