from datetime import datetime

from pydantic import BaseModel, EmailStr


# ── User Auth ──


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str | None
    role: str

    model_config = {"from_attributes": True}


class NetworkBrief(BaseModel):
    id: int
    name: str
    slug: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    user: UserOut
    networks: list[NetworkBrief]


class InviteRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None
    network_ids: list[int] = []


# ── Instagram OAuth (existing) ──


class OAuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class OAuthCallbackResponse(BaseModel):
    access_token: str
    ig_user_id: str
    username: str
    name: str | None = None
    profile_picture_url: str | None = None


class OAuthSaveRequest(BaseModel):
    profile_id: int
    ig_user_id: str
    username: str
    access_token: str
    name: str | None = None
    profile_picture_url: str | None = None


class OAuthTokenOut(BaseModel):
    id: int
    profile_id: int
    ig_user_id: str | None
    saved_at: datetime

    model_config = {"from_attributes": True}
