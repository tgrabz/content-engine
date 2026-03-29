from datetime import datetime

from pydantic import BaseModel


class EditSessionOut(BaseModel):
    id: int
    video_id: int
    profile_id: int
    template_id: int | None
    scene_json: str
    crop_box: str
    padding_pct: float
    offset_x: float
    offset_y: float
    caption_text: str
    caption_color: str
    caption_box: str
    caption_placement: str
    post_caption: str
    render_quality: str
    include_audio: bool
    exported_path: str | None
    profile_status: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EditSessionUpdate(BaseModel):
    template_id: int | None = None
    scene_json: str | None = None
    crop_box: str | None = None
    padding_pct: float | None = None
    offset_x: float | None = None
    offset_y: float | None = None
    caption_text: str | None = None
    caption_color: str | None = None
    caption_box: str | None = None
    caption_placement: str | None = None
    post_caption: str | None = None
    render_quality: str | None = None
    include_audio: bool | None = None
    exported_path: str | None = None
    profile_status: str | None = None
