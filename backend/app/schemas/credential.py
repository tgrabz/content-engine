from datetime import datetime

from pydantic import BaseModel


class CredentialCreate(BaseModel):
    username: str
    password: str


class CredentialOut(BaseModel):
    id: int
    username: str
    created_at: datetime

    model_config = {"from_attributes": True}
