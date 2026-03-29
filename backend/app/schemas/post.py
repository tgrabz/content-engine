from datetime import datetime

from pydantic import BaseModel


class PostQueueCreate(BaseModel):
    video_id: int
    profile_id: int
    caption: str = ""
    share_to_feed: bool = True
    thumb_offset_ms: int = 0
    auto_schedule: bool = True  # auto-assign next schedule slot if profile has schedule


class PostQueueUpdate(BaseModel):
    caption: str | None = None
    share_to_feed: bool | None = None
    thumb_offset_ms: int | None = None
    position: int | None = None


class PostQueueOut(BaseModel):
    id: int
    video_id: int
    profile_id: int
    caption: str
    share_to_feed: bool
    thumb_offset_ms: int
    upload_strategy: str
    status: str
    ig_container_id: str | None
    ig_media_id: str | None
    ig_permalink: str | None
    error_message: str | None
    position: int
    scheduled_for: datetime | None
    created_at: datetime
    published_at: datetime | None

    model_config = {"from_attributes": True}
