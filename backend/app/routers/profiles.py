import json
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.profile import Profile
from app.schemas.profile import ProfileCreate, ProfileOut, ProfileUpdate

router = APIRouter()


@router.get("", response_model=list[ProfileOut])
def list_profiles(network_id: int | None = Query(None), db: Session = Depends(get_db)):
    q = db.query(Profile)
    if network_id is not None:
        q = q.filter(Profile.network_id == network_id)
    return q.order_by(Profile.name).all()


@router.post("", response_model=ProfileOut, status_code=201)
def create_profile(body: ProfileCreate, network_id: int | None = Query(None), db: Session = Depends(get_db)):
    q = db.query(Profile).filter(Profile.name == body.name)
    if network_id is not None:
        q = q.filter(Profile.network_id == network_id)
    if q.first():
        raise HTTPException(400, f"Profile '{body.name}' already exists")
    profile = Profile(name=body.name, niche_id=body.niche_id, export_dir=body.export_dir, network_id=network_id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: int, body: ProfileUpdate, db: Session = Depends(get_db)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    data = body.model_dump(exclude_unset=True)
    # Serialize schedule_times list → JSON string for storage
    if "schedule_times" in data and data["schedule_times"] is not None:
        data["schedule_times"] = json.dumps(data["schedule_times"])
    for field, value in data.items():
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


# ──── Username availability checker ────


class UsernameCheckRequest(BaseModel):
    usernames: list[str]


class UsernameCheckResult(BaseModel):
    username: str
    available: bool
    error: str | None = None


@router.post("/check-usernames", response_model=list[UsernameCheckResult])
async def check_usernames(body: UsernameCheckRequest):
    results = []
    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "X-IG-App-ID": "936619743392459",
        },
        timeout=10.0,
    ) as client:
        for username in body.usernames[:20]:
            username = username.strip().lower().lstrip("@")
            if not username or len(username) < 1:
                continue
            try:
                resp = await client.get(
                    f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
                )
                available = resp.status_code == 404
                results.append(UsernameCheckResult(username=username, available=available))
            except Exception as e:
                results.append(UsernameCheckResult(username=username, available=False, error=str(e)[:100]))
    return results
