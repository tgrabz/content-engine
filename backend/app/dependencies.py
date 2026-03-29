"""Shared FastAPI dependencies for auth and network access."""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import Network, User, UserNetwork
from app.services.auth_service import decode_access_token


async def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header. Raises 401 if invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    token = authorization[7:]
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def get_optional_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of raising 401."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception:
        return None
    return db.get(User, user_id)


def require_network_access(
    user: User,
    network_id: int,
    db: Session,
) -> Network:
    """Verify user has access to a network. Owner bypasses check. Returns the Network."""
    network = db.get(Network, network_id)
    if not network:
        raise HTTPException(404, "Network not found")
    if user.role == "owner":
        return network
    membership = (
        db.query(UserNetwork)
        .filter(UserNetwork.user_id == user.id, UserNetwork.network_id == network_id)
        .first()
    )
    if not membership:
        raise HTTPException(403, "No access to this network")
    return network


async def get_auth(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
    db: Session = Depends(get_db),
) -> tuple[User | None, Network | None]:
    """Accept either JWT (browser) or API key (local app).
    Returns (user, network) — at least one will be set on success.
    """
    # Try JWT first
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            payload = decode_access_token(token)
            user_id = int(payload["sub"])
            user = db.get(User, user_id)
            if user:
                return (user, None)
        except Exception:
            pass

    # Try API key
    if x_api_key:
        network = db.query(Network).filter(Network.api_key == x_api_key).first()
        if network:
            return (None, network)

    raise HTTPException(401, "Not authenticated")
