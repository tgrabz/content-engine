from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        Index("idx_videos_niche", "niche_id"),
        Index("idx_videos_status", "status"),
        Index("idx_videos_source", "source_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    network_id: Mapped[int | None] = mapped_column(ForeignKey("networks.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(20), default="instagram")
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id", ondelete="CASCADE"))
    source_account: Mapped[str] = mapped_column(String(100), nullable=False)
    shortcode: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    local_path: Mapped[str | None] = mapped_column(Text)
    file_bytes: Mapped[int] = mapped_column(default=0)
    views: Mapped[int | None] = mapped_column()
    caption: Mapped[str] = mapped_column(Text, default="")
    duration_sec: Mapped[float | None] = mapped_column()
    width: Mapped[int | None] = mapped_column()
    height: Mapped[int | None] = mapped_column()

    # AI analysis (cached — shared across all profiles using this video)
    ai_description: Mapped[str | None] = mapped_column(Text, default=None)

    # Perceptual hash for cross-account duplicate detection
    video_hash: Mapped[str | None] = mapped_column(String(64), default=None)

    # Workflow: downloaded → editing → ready → queued → posting → posted
    status: Mapped[str] = mapped_column(String(20), default="downloaded")

    # Editing
    edit_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("edit_sessions.id", ondelete="SET NULL")
    )
    exported_path: Mapped[str | None] = mapped_column(Text)

    # Posting
    ig_post_id: Mapped[str | None] = mapped_column(String(50))
    ig_permalink: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column()
    posted_by_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )

    scraped_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
