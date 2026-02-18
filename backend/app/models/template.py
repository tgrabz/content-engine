from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)  # path to PNG overlay
    # Normalized geometry [x1, y1, x2, y2] as JSON strings
    video_box: Mapped[str] = mapped_column(Text, default="[0.06, 0.18, 0.94, 0.94]")
    caption_box: Mapped[str] = mapped_column(Text, default="[0.06, 0.08, 0.94, 0.16]")
    overlays_json: Mapped[str] = mapped_column(Text, default="[]")
    text_config: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
