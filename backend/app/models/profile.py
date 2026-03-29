from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("network_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    network_id: Mapped[int | None] = mapped_column(ForeignKey("networks.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    niche_id: Mapped[int | None] = mapped_column(ForeignKey("niches.id", ondelete="SET NULL"))
    export_dir: Mapped[str] = mapped_column(String(255), nullable=False)
    default_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    # ── Schedule config ──
    schedule_times: Mapped[str | None] = mapped_column(Text, default=None)  # JSON: ["09:00","14:00","19:00"]
    daily_post_limit: Mapped[int] = mapped_column(default=3)
    warmup_started_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
