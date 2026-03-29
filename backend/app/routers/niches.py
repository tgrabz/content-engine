from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.niche import Niche, NicheAccount
from app.schemas.niche import NicheCreate, NicheOut, NicheUpdate

router = APIRouter()


@router.get("", response_model=list[NicheOut])
def list_niches(network_id: int | None = Query(None), db: Session = Depends(get_db)):
    q = db.query(Niche)
    if network_id is not None:
        q = q.filter(Niche.network_id == network_id)
    return q.order_by(Niche.name).all()


@router.post("", response_model=NicheOut, status_code=201)
def create_niche(body: NicheCreate, network_id: int | None = Query(None), db: Session = Depends(get_db)):
    q = db.query(Niche).filter(Niche.name == body.name)
    if network_id is not None:
        q = q.filter(Niche.network_id == network_id)
    if q.first():
        raise HTTPException(400, f"Niche '{body.name}' already exists")
    niche = Niche(name=body.name, network_id=network_id)
    for username in body.accounts:
        niche.accounts.append(NicheAccount(username=username.strip().lstrip("@")))
    db.add(niche)
    db.commit()
    db.refresh(niche)
    return niche


@router.get("/{niche_id}", response_model=NicheOut)
def get_niche(niche_id: int, db: Session = Depends(get_db)):
    niche = db.get(Niche, niche_id)
    if not niche:
        raise HTTPException(404, "Niche not found")
    return niche


@router.put("/{niche_id}", response_model=NicheOut)
def update_niche(niche_id: int, body: NicheUpdate, db: Session = Depends(get_db)):
    niche = db.get(Niche, niche_id)
    if not niche:
        raise HTTPException(404, "Niche not found")
    if body.name is not None:
        niche.name = body.name
    if body.accounts is not None:
        db.query(NicheAccount).filter(NicheAccount.niche_id == niche_id).delete()
        for username in body.accounts:
            niche.accounts.append(NicheAccount(username=username.strip().lstrip("@")))
    db.commit()
    db.refresh(niche)
    return niche


@router.delete("/{niche_id}", status_code=204)
def delete_niche(niche_id: int, db: Session = Depends(get_db)):
    niche = db.get(Niche, niche_id)
    if not niche:
        raise HTTPException(404, "Niche not found")
    db.delete(niche)
    db.commit()
