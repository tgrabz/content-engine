"""Network CRUD router."""

import base64
import hashlib
import re
import secrets

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import Network, User, UserNetwork
from app.schemas.network import NetworkCreate, NetworkMemberOut, NetworkOut, NetworkUpdate

router = APIRouter()


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "network"


@router.get("", response_model=list[NetworkOut])
def list_networks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "owner":
        return db.query(Network).order_by(Network.name).all()
    return (
        db.query(Network)
        .join(UserNetwork)
        .filter(UserNetwork.user_id == user.id)
        .order_by(Network.name)
        .all()
    )


@router.post("", response_model=NetworkOut)
def create_network(
    body: NetworkCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "owner":
        raise HTTPException(403, "Only the owner can create networks")

    slug = _slugify(body.name)
    # Ensure unique slug
    existing = db.query(Network).filter(Network.slug == slug).first()
    if existing:
        slug = f"{slug}-{secrets.token_hex(3)}"

    f = _get_fernet()
    network = Network(
        name=body.name,
        slug=slug,
        ig_app_id=body.ig_app_id or None,
        ig_app_secret_enc=f.encrypt(body.ig_app_secret.encode()).decode() if body.ig_app_secret else None,
        ig_redirect_uri=body.ig_redirect_uri or None,
        public_url=body.public_url or None,
        api_key=secrets.token_hex(32),
    )
    db.add(network)
    db.flush()

    # Auto-assign creator as admin
    db.add(UserNetwork(user_id=user.id, network_id=network.id, role="admin"))
    db.commit()
    db.refresh(network)
    return network


@router.get("/{network_id}", response_model=NetworkOut)
def get_network(
    network_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.dependencies import require_network_access
    network = require_network_access(user, network_id, db)
    return network


@router.put("/{network_id}", response_model=NetworkOut)
def update_network(
    network_id: int,
    body: NetworkUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "owner":
        raise HTTPException(403, "Only the owner can update networks")

    network = db.get(Network, network_id)
    if not network:
        raise HTTPException(404, "Network not found")

    if body.name is not None:
        network.name = body.name
    if body.ig_app_id is not None:
        network.ig_app_id = body.ig_app_id
    if body.ig_app_secret is not None:
        f = _get_fernet()
        network.ig_app_secret_enc = f.encrypt(body.ig_app_secret.encode()).decode()
    if body.ig_redirect_uri is not None:
        network.ig_redirect_uri = body.ig_redirect_uri
    if body.public_url is not None:
        network.public_url = body.public_url

    db.commit()
    db.refresh(network)
    return network


@router.delete("/{network_id}", status_code=204)
def delete_network(
    network_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "owner":
        raise HTTPException(403, "Only the owner can delete networks")
    network = db.get(Network, network_id)
    if not network:
        raise HTTPException(404, "Network not found")
    db.delete(network)
    db.commit()


@router.post("/{network_id}/members", response_model=NetworkMemberOut)
def add_member(
    network_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "owner":
        raise HTTPException(403, "Only the owner can manage members")
    network = db.get(Network, network_id)
    if not network:
        raise HTTPException(404, "Network not found")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")

    existing = (
        db.query(UserNetwork)
        .filter(UserNetwork.user_id == user_id, UserNetwork.network_id == network_id)
        .first()
    )
    if existing:
        raise HTTPException(400, "User already a member")

    membership = UserNetwork(user_id=user_id, network_id=network_id, role="member")
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return NetworkMemberOut(
        id=membership.id,
        user_id=membership.user_id,
        network_id=membership.network_id,
        role=membership.role,
        email=target.email,
        display_name=target.display_name,
    )


@router.get("/{network_id}/members", response_model=list[NetworkMemberOut])
def list_members(
    network_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.dependencies import require_network_access
    require_network_access(user, network_id, db)

    memberships = (
        db.query(UserNetwork, User)
        .join(User)
        .filter(UserNetwork.network_id == network_id)
        .all()
    )
    return [
        NetworkMemberOut(
            id=m.id, user_id=m.user_id, network_id=m.network_id,
            role=m.role, email=u.email, display_name=u.display_name,
        )
        for m, u in memberships
    ]


@router.delete("/{network_id}/members/{user_id}", status_code=204)
def remove_member(
    network_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "owner":
        raise HTTPException(403, "Only the owner can manage members")
    membership = (
        db.query(UserNetwork)
        .filter(UserNetwork.user_id == user_id, UserNetwork.network_id == network_id)
        .first()
    )
    if membership:
        db.delete(membership)
        db.commit()


@router.post("/{network_id}/rotate-api-key", response_model=NetworkOut)
def rotate_api_key(
    network_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "owner":
        raise HTTPException(403, "Only the owner can rotate API keys")
    network = db.get(Network, network_id)
    if not network:
        raise HTTPException(404, "Network not found")
    network.api_key = secrets.token_hex(32)
    db.commit()
    db.refresh(network)
    return network
