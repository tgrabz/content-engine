from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class EditSession(Base):
    __tablename__ = "edit_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    # Full Fabric.js scene state
    scene_json: Mapped[str] = mapped_column(Text, default="{}")
    # Crop (normalized x1, y1, x2, y2)
    crop_box: Mapped[str] = mapped_column(Text, default="[0.08, 0.12, 0.92, 0.92]")
    padding_pct: Mapped[float] = mapped_column(default=6.0)
    offset_x: Mapped[float] = mapped_column(default=0.0)
    offset_y: Mapped[float] = mapped_column(default=0.0)
    # Caption
    caption_text: Mapped[str] = mapped_column(Text, default="")
    caption_color: Mapped[str] = mapped_column(String(10), default="#000000")
    caption_placement: Mapped[str] = mapped_column(String(10), default="auto")
    # Render
    render_quality: Mapped[str] = mapped_column(String(20), default="Native 1920")
    include_audio: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
