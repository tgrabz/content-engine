import io
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.template import Template
from app.schemas.template import TemplateOut, TemplateUpdate
from app.services.template_generator import (
    generate_template_image,
    GENERATED_VIDEO_BOX,
    GENERATED_CAPTION_BOX,
)

router = APIRouter()


@router.get("", response_model=list[TemplateOut])
def list_templates(
    profile_id: int | None = None, network_id: int | None = Query(None), db: Session = Depends(get_db)
):
    q = db.query(Template)
    if network_id is not None:
        q = q.filter(Template.network_id == network_id)
    if profile_id is not None:
        q = q.filter(
            (Template.profile_id == profile_id) | (Template.profile_id.is_(None))
        )
    return q.order_by(Template.name).all()


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    name: str = Form(...),
    video_box: str = Form("[0.06, 0.18, 0.94, 0.94]"),
    caption_box: str = Form("[0.06, 0.08, 0.94, 0.16]"),
    profile_id: int | None = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Save image file
    ts = int(time.time() * 1000)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    ext = Path(image.filename or "template.png").suffix or ".png"
    filename = f"{ts}_{safe_name}{ext}"
    filepath = settings.templates_dir / filename
    content = await image.read()
    filepath.write_bytes(content)

    tmpl = Template(
        name=name,
        image_path=str(filepath),
        video_box=video_box,
        caption_box=caption_box,
        profile_id=profile_id,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.post("/generate", response_model=TemplateOut, status_code=201)
async def generate_template(
    name: str = Form(...),
    display_name: str = Form(...),
    handle: str = Form(...),
    verified: bool = Form(True),
    profile_id: int | None = Form(None),
    pfp: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Generate a template PNG programmatically from profile branding info."""
    pfp_bytes = await pfp.read()
    pfp_img = Image.open(io.BytesIO(pfp_bytes)).convert("RGBA")

    template_img = generate_template_image(
        display_name=display_name,
        handle=handle,
        pfp_image=pfp_img,
        verified=verified,
    )

    # Save to filesystem
    ts = int(time.time() * 1000)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    filename = f"{ts}_{safe_name}.png"
    filepath = settings.templates_dir / filename
    template_img.save(str(filepath), "PNG")

    tmpl = Template(
        name=name,
        image_path=str(filepath),
        video_box=GENERATED_VIDEO_BOX,
        caption_box=GENERATED_CAPTION_BOX,
        profile_id=profile_id,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(template_id: int, db: Session = Depends(get_db)):
    tmpl = db.get(Template, template_id)
    if not tmpl:
        raise HTTPException(404, "Template not found")
    return tmpl


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int, body: TemplateUpdate, db: Session = Depends(get_db)
):
    tmpl = db.get(Template, template_id)
    if not tmpl:
        raise HTTPException(404, "Template not found")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(tmpl, key, val)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    tmpl = db.get(Template, template_id)
    if not tmpl:
        raise HTTPException(404, "Template not found")
    # Clean up image file
    p = Path(tmpl.image_path)
    if p.exists():
        p.unlink()
    db.delete(tmpl)
    db.commit()


@router.get("/{template_id}/image")
def get_template_image(template_id: int, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse

    tmpl = db.get(Template, template_id)
    if not tmpl:
        raise HTTPException(404, "Template not found")
    p = Path(tmpl.image_path)
    if not p.exists():
        raise HTTPException(404, "Image file not found")
    return FileResponse(str(p), media_type="image/png")
