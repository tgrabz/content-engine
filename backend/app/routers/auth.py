"""Auth router — user auth (register/login) + Instagram Platform API OAuth."""

import base64
import hashlib
import io
import logging
import secrets
import time

import requests as http_requests
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from PIL import Image
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.credential import OAuthToken
from app.models.profile import Profile
from app.models.template import Template
from app.models.user import Network, User, UserNetwork
from app.schemas.auth import (
    AuthResponse,
    InviteRequest,
    LoginRequest,
    NetworkBrief,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    OAuthSaveRequest,
    OAuthTokenOut,
    OAuthUrlResponse,
    RegisterRequest,
    UserOut,
)
from app.services.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.services.oauth_service import (
    build_auth_url,
    exchange_code_for_token,
    exchange_long_lived_token,
    get_ig_user_info,
)
from app.services.template_generator import (
    generate_template_image,
    GENERATED_VIDEO_BOX,
    GENERATED_CAPTION_BOX,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── User Auth ──


def _user_networks(db: Session, user: User) -> list[NetworkBrief]:
    """Get networks a user has access to."""
    if user.role == "owner":
        networks = db.query(Network).order_by(Network.name).all()
    else:
        networks = (
            db.query(Network)
            .join(UserNetwork)
            .filter(UserNetwork.user_id == user.id)
            .order_by(Network.name)
            .all()
        )
    return [NetworkBrief.model_validate(n) for n in networks]


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    """Check if any users exist (for first-time setup detection)."""
    has_users = db.query(User).first() is not None
    return {"has_users": has_users}


@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user. First user becomes owner."""
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(400, "Email already registered")

    is_first = db.query(User).first() is None
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role="owner" if is_first else "member",
    )
    db.add(user)
    db.flush()

    # First user gets assigned to all existing networks
    if is_first:
        for network in db.query(Network).all():
            db.add(UserNetwork(user_id=user.id, network_id=network.id, role="admin"))

    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user=UserOut.model_validate(user),
        networks=_user_networks(db, user),
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Login with email + password."""
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user=UserOut.model_validate(user),
        networks=_user_networks(db, user),
    )


@router.get("/me", response_model=AuthResponse)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get current user info + networks."""
    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user=UserOut.model_validate(user),
        networks=_user_networks(db, user),
    )


@router.post("/invite", response_model=UserOut)
def invite_user(
    body: InviteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owner invites a new member, optionally assigning them to networks."""
    if user.role != "owner":
        raise HTTPException(403, "Only the owner can invite users")

    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(400, "Email already registered")

    new_user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role="member",
    )
    db.add(new_user)
    db.flush()

    for nid in body.network_ids:
        network = db.get(Network, nid)
        if network:
            db.add(UserNetwork(user_id=new_user.id, network_id=nid, role="member"))

    db.commit()
    db.refresh(new_user)
    return UserOut.model_validate(new_user)

# In-memory state for CSRF protection (simple for single-server)
_oauth_states: dict[str, bool] = {}


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


@router.get("/oauth/url", response_model=OAuthUrlResponse)
def get_oauth_url(network_id: int | None = None, db: Session = Depends(get_db)):
    """Generate Instagram OAuth authorization URL. Uses per-network IG credentials."""
    ig_app_id = settings.ig_app_id
    ig_redirect_uri = settings.ig_redirect_uri

    if network_id:
        network = db.get(Network, network_id)
        if network and network.ig_app_id:
            ig_app_id = network.ig_app_id
        if network and network.ig_redirect_uri:
            ig_redirect_uri = network.ig_redirect_uri

    if not ig_app_id:
        raise HTTPException(400, "Instagram App ID not configured")
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = True
    auth_url = build_auth_url(ig_app_id, ig_redirect_uri, state)
    return {"auth_url": auth_url, "state": state}


@router.post("/oauth/callback", response_model=OAuthCallbackResponse)
def handle_oauth_callback(body: OAuthCallbackRequest, network_id: int | None = None, db: Session = Depends(get_db)):
    """Exchange OAuth code for tokens and get Instagram user info."""
    # Validate state
    if body.state not in _oauth_states:
        raise HTTPException(400, "Invalid OAuth state")
    _oauth_states.pop(body.state, None)

    # Resolve IG credentials (per-network or fallback to .env)
    ig_app_id = settings.ig_app_id
    ig_app_secret = settings.ig_app_secret
    ig_redirect_uri = settings.ig_redirect_uri

    if network_id:
        network = db.get(Network, network_id)
        if network:
            if network.ig_app_id:
                ig_app_id = network.ig_app_id
            if network.ig_app_secret_enc:
                f = _get_fernet()
                ig_app_secret = f.decrypt(network.ig_app_secret_enc.encode()).decode()
            if network.ig_redirect_uri:
                ig_redirect_uri = network.ig_redirect_uri

    if not ig_app_id or not ig_app_secret:
        raise HTTPException(400, "Instagram App credentials not configured")

    try:
        # Exchange code for short-lived token
        short = exchange_code_for_token(
            ig_app_id,
            ig_app_secret,
            ig_redirect_uri,
            body.code,
        )
        short_token = short["access_token"]
        ig_user_id = str(short.get("user_id", ""))

        # Exchange for long-lived token (~60 days)
        long_lived = exchange_long_lived_token(
            ig_app_secret,
            short_token,
        )

        # Get user profile info
        user_info = get_ig_user_info(long_lived["access_token"])

        return OAuthCallbackResponse(
            access_token=long_lived["access_token"],
            ig_user_id=ig_user_id or str(user_info.get("user_id", "")),
            username=user_info.get("username", ""),
            name=user_info.get("name"),
            profile_picture_url=user_info.get("profile_picture_url"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"OAuth flow failed: {e}")


@router.post("/oauth/save", response_model=OAuthTokenOut)
def save_oauth_tokens(body: OAuthSaveRequest, db: Session = Depends(get_db)):
    """Save OAuth tokens for a profile. Auto-generates a template from the IG profile picture."""
    f = _get_fernet()

    # Upsert: remove existing token for this profile
    existing = (
        db.query(OAuthToken)
        .filter(OAuthToken.profile_id == body.profile_id)
        .first()
    )
    if existing:
        db.delete(existing)
        db.flush()

    token = OAuthToken(
        profile_id=body.profile_id,
        ig_user_id=body.ig_user_id,
        user_access_token_enc=f.encrypt(body.access_token.encode()).decode(),
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    # Auto-generate template from Instagram name + profile picture
    if body.profile_picture_url and body.username:
        try:
            _auto_generate_template(db, body.profile_id, body.username, body.name, body.profile_picture_url)
        except Exception:
            logger.exception("Auto-template generation failed (non-fatal)")

    return token


def _auto_generate_template(
    db: Session, profile_id: int, username: str, display_name: str | None, pfp_url: str
) -> None:
    """Download profile picture and generate a branded template."""
    # Download profile picture
    resp = http_requests.get(pfp_url, timeout=15)
    resp.raise_for_status()
    pfp_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")

    name = display_name or username
    template_img = generate_template_image(
        display_name=name,
        handle=username,
        pfp_image=pfp_img,
        verified=True,
    )

    # Save PNG to disk
    ts = int(time.time() * 1000)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    filename = f"{ts}_{safe_name}.png"
    filepath = settings.templates_dir / filename
    template_img.save(str(filepath), "PNG")

    # Create template record
    tmpl = Template(
        name=f"{name}",
        image_path=str(filepath),
        video_box=GENERATED_VIDEO_BOX,
        caption_box=GENERATED_CAPTION_BOX,
        profile_id=profile_id,
    )
    db.add(tmpl)
    db.flush()

    # Set as profile's default template
    profile = db.get(Profile, profile_id)
    if profile:
        profile.default_template_id = tmpl.id

    db.commit()
    logger.info(f"Auto-generated template '{tmpl.name}' (id={tmpl.id}) for profile {profile_id}")


@router.post("/oauth/generate-template/{profile_id}", response_model=OAuthTokenOut)
def generate_template_for_profile(profile_id: int, db: Session = Depends(get_db)):
    """Fetch IG profile info using stored token and auto-generate a template."""
    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.profile_id == profile_id)
        .first()
    )
    if not token:
        raise HTTPException(404, "No OAuth token for this profile")

    # Decrypt token
    f = _get_fernet()
    access_token = f.decrypt(
        (token.user_access_token_enc or token.page_access_token_enc or "").encode()
    ).decode()

    # Fetch user info from Instagram
    user_info = get_ig_user_info(access_token)
    username = user_info.get("username", "")
    name = user_info.get("name")
    pfp_url = user_info.get("profile_picture_url")

    if not pfp_url:
        raise HTTPException(400, "Instagram did not return a profile picture URL")

    _auto_generate_template(db, profile_id, username, name, pfp_url)
    return token


@router.get("/oauth/token/{profile_id}", response_model=OAuthTokenOut | None)
def get_profile_token(profile_id: int, db: Session = Depends(get_db)):
    """Check if a profile has OAuth tokens saved."""
    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.profile_id == profile_id)
        .first()
    )
    if not token:
        return None
    return token


@router.delete("/oauth/token/{profile_id}", status_code=204)
def delete_profile_token(profile_id: int, db: Session = Depends(get_db)):
    """Remove OAuth tokens for a profile."""
    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.profile_id == profile_id)
        .first()
    )
    if token:
        db.delete(token)
        db.commit()
