from datetime import datetime

from pydantic import BaseModel


class VideoOut(BaseModel):
    id: int
    platform: str
    niche_id: int
    source_account: str
    shortcode: str
    source_url: str
    local_path: str | None
    file_bytes: int
    views: int | None
    caption: str
    duration_sec: float | None
    width: int | None
    height: int | None
    status: str
    exported_path: str | None
    ig_post_id: str | None
    scraped_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VideoUpdate(BaseModel):
    status: str | None = None
    caption: str | None = None
