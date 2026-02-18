import base64
import hashlib

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.credential import IGLoginCredential
from app.schemas.credential import CredentialCreate, CredentialOut

router = APIRouter()


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


@router.get("", response_model=list[CredentialOut])
def list_credentials(db: Session = Depends(get_db)):
    return db.query(IGLoginCredential).order_by(IGLoginCredential.username).all()


@router.post("", response_model=CredentialOut, status_code=201)
def create_credential(body: CredentialCreate, db: Session = Depends(get_db)):
    existing = db.query(IGLoginCredential).filter(
        IGLoginCredential.username == body.username
    ).first()
    if existing:
        raise HTTPException(400, f"Credential for '{body.username}' already exists")
    f = _get_fernet()
    cred = IGLoginCredential(
        username=body.username,
        password_enc=f.encrypt(body.password.encode()).decode(),
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


@router.delete("/{cred_id}", status_code=204)
def delete_credential(cred_id: int, db: Session = Depends(get_db)):
    cred = db.get(IGLoginCredential, cred_id)
    if not cred:
        raise HTTPException(404, "Credential not found")
    db.delete(cred)
    db.commit()
