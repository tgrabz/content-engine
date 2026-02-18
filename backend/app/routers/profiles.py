from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.profile import Profile
from app.schemas.profile import ProfileCreate, ProfileOut, ProfileUpdate

router = APIRouter()


@router.get("", response_model=list[ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    return db.query(Profile).order_by(Profile.name).all()


@router.post("", response_model=ProfileOut, status_code=201)
def create_profile(body: ProfileCreate, db: Session = Depends(get_db)):
    if db.query(Profile).filter(Profile.name == body.name).first():
        raise HTTPException(400, f"Profile '{body.name}' already exists")
    profile = Profile(name=body.name, niche_id=body.niche_id, export_dir=body.export_dir)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: int, body: ProfileUpdate, db: Session = Depends(get_db)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    db.delete(profile)
    db.commit()
