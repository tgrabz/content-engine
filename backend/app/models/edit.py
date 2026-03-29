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
    crop_box: Mapped[str] = mapped_column(Text, default="[0, 0, 1, 1]")
    padding_pct: Mapped[float] = mapped_column(default=6.0)
    offset_x: Mapped[float] = mapped_column(default=0.0)
    offset_y: Mapped[float] = mapped_column(default=0.0)
    # Caption (overlay text rendered inside the video)
    caption_text: Mapped[str] = mapped_column(Text, default="")
    caption_color: Mapped[str] = mapped_column(String(10), default="#000000")
    caption_box: Mapped[str] = mapped_column(Text, default="")  # overrides template if set
    caption_placement: Mapped[str] = mapped_column(String(10), default="auto")
    # Post caption (Instagram caption, separate from overlay text)
    post_caption: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Render
    render_quality: Mapped[str] = mapped_column(String(20), default="Native 1920")
    include_audio: Mapped[bool] = mapped_column(default=False)
    # Per-profile state (allows different status/export per profile)
    exported_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
