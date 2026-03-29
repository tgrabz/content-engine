from datetime import datetime

from pydantic import BaseModel


class NetworkCreate(BaseModel):
    name: str
    ig_app_id: str = ""
    ig_app_secret: str = ""  # plain text, encrypted on save
    ig_redirect_uri: str = "https://localhost:5173/auth/callback"
    public_url: str = ""


class NetworkUpdate(BaseModel):
    name: str | None = None
    ig_app_id: str | None = None
    ig_app_secret: str | None = None  # plain text, encrypted on save
    ig_redirect_uri: str | None = None
    public_url: str | None = None


class NetworkOut(BaseModel):
    id: int
    name: str
    slug: str
    ig_app_id: str | None
    ig_redirect_uri: str | None
    public_url: str | None
    api_key: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NetworkMemberOut(BaseModel):
    id: int
    user_id: int
    network_id: int
    role: str
    email: str
    display_name: str | None

    model_config = {"from_attributes": True}
