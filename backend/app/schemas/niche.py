from datetime import datetime

from pydantic import BaseModel


class NicheAccountOut(BaseModel):
    id: int
    username: str
    platform: str

    model_config = {"from_attributes": True}


class NicheCreate(BaseModel):
    name: str
    accounts: list[str] = []


class NicheUpdate(BaseModel):
    name: str | None = None
    accounts: list[str] | None = None


class NicheOut(BaseModel):
    id: int
    name: str
    accounts: list[NicheAccountOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
