from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class PostQueue(Base):
    __tablename__ = "post_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    caption: Mapped[str] = mapped_column(Text, default="")
    share_to_feed: Mapped[bool] = mapped_column(default=True)
    thumb_offset_ms: Mapped[int] = mapped_column(default=0)
    upload_strategy: Mapped[str] = mapped_column(String(20), default="resumable")
    # queued → uploading → processing → published → failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    ig_container_id: Mapped[str | None] = mapped_column(String(50))
    ig_media_id: Mapped[str | None] = mapped_column(String(50))
    ig_permalink: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(default=0)
    scheduled_for: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    published_at: Mapped[datetime | None] = mapped_column()
