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


class ProfileOut(BaseModel):
    id: int
    name: str
    niche_id: int | None
    export_dir: str
    default_template_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
