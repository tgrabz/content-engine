from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    network_id: Mapped[int | None] = mapped_column(ForeignKey("networks.id", ondelete="CASCADE"))
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    login_credential_id: Mapped[int] = mapped_column(
        ForeignKey("ig_login_credentials.id")
    )
    # pending → running → completed → failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_accounts: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    results_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
