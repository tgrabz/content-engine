from datetime import datetime

from pydantic import BaseModel


class ProfileCreate(BaseModel):
    name: str
    niche_id: int | None = None
    export_dir: str = "default"


class ProfileUpdate(BaseModel):
    name: str | None = None
    niche_id: int | None = None
    export_dir: str | None = None
    default_template_id: int | None = None
    schedule_times: list[str] | None = None  # ["09:00", "14:00", "19:00"]
    daily_post_limit: int | None = None
    warmup_started_at: datetime | None = None


class ProfileOut(BaseModel):
    id: int
    name: str
    niche_id: int | None
    export_dir: str
    default_template_id: int | None
    schedule_times: str | None
    daily_post_limit: int
    warmup_started_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
