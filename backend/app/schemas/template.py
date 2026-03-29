from datetime import datetime

from pydantic import BaseModel


class TemplateOut(BaseModel):
    id: int
    profile_id: int | None
    name: str
    image_path: str
    video_box: str
    caption_box: str
    overlays_json: str
    text_config: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateUpdate(BaseModel):
    name: str | None = None
    video_box: str | None = None
    caption_box: str | None = None
    profile_id: int | None = None
    overlays_json: str | None = None
    text_config: str | None = None
