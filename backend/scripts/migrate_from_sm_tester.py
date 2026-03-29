#!/usr/bin/env python3
"""Migrate data from sm-tester-polished into content-engine's SQLite DB.

Usage:
    cd backend
    python scripts/migrate_from_sm_tester.py [--source /path/to/sm-tester-polished]

Imports:
    - Niches + accounts from scraper_config.json
    - IG login credentials from .secrets/ig_accounts.json
    - Editor profiles from .secrets/editor_profiles.json
    - Templates (PNG + JSON sidecar) from templates/
    - Videos from downloads/ (registers file paths, sets status=downloaded)
"""

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, engine, Base
from app.models.niche import Niche, NicheAccount
from app.models.credential import IGLoginCredential
from app.models.profile import Profile
from app.models.template import Template
from app.models.video import Video


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def migrate(source_dir: Path, db: Session):
    print(f"Migrating from: {source_dir}")
    print(f"Into database:  {settings.database_url}")
    print()

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    # ── 1. Niches + accounts ──
    config_path = source_dir / "scraper_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        niches_data = config.get("niches", {})
        for niche_name, accounts in niches_data.items():
            existing = db.query(Niche).filter(Niche.name == niche_name).first()
            if existing:
                print(f"  [skip] Niche '{niche_name}' already exists (id={existing.id})")
                niche = existing
            else:
                niche = Niche(name=niche_name)
                db.add(niche)
                db.flush()
                print(f"  [+] Niche '{niche_name}' (id={niche.id})")

            for username in accounts:
                exists = (
                    db.query(NicheAccount)
                    .filter(NicheAccount.niche_id == niche.id, NicheAccount.username == username)
                    .first()
                )
                if not exists:
                    db.add(NicheAccount(niche_id=niche.id, username=username))
                    print(f"    [+] Account @{username}")
                else:
                    print(f"    [skip] Account @{username}")
        db.commit()
    else:
        print("  [!] scraper_config.json not found, skipping niches")

    # ── 2. IG login credentials ──
    ig_accounts_path = source_dir / ".secrets" / "ig_accounts.json"
    if ig_accounts_path.exists():
        ig_accounts = json.loads(ig_accounts_path.read_text())
        for username, val in ig_accounts.items():
            # Handle both formats: {"user": "x", "pass": "y"} or just "password"
            if isinstance(val, dict):
                password = val.get("pass", "")
            else:
                password = str(val)

            existing = db.query(IGLoginCredential).filter(
                IGLoginCredential.username == username
            ).first()
            if existing:
                print(f"  [skip] Credential for @{username}")
            else:
                db.add(IGLoginCredential(
                    username=username,
                    password_enc=_encrypt(password),
                ))
                print(f"  [+] Credential for @{username}")
        db.commit()
    else:
        print("  [!] ig_accounts.json not found, skipping credentials")

    # ── 3. Profiles ──
    profiles_path = source_dir / ".secrets" / "editor_profiles.json"
    profile_map: dict[str, Profile] = {}  # name → Profile obj
    if profiles_path.exists():
        profiles_data = json.loads(profiles_path.read_text())
        for profile_name, info in profiles_data.items():
            existing = db.query(Profile).filter(Profile.name == profile_name).first()
            if existing:
                print(f"  [skip] Profile '{profile_name}' (id={existing.id})")
                profile_map[profile_name] = existing
            else:
                # Resolve niche ID
                niche_name = info.get("niche", "")
                niche = db.query(Niche).filter(Niche.name.ilike(f"%{niche_name}%")).first() if niche_name else None

                export_dir = info.get("dir", f"exports/{profile_name}")
                profile = Profile(
                    name=profile_name,
                    niche_id=niche.id if niche else None,
                    export_dir=export_dir,
                )
                db.add(profile)
                db.flush()
                print(f"  [+] Profile '{profile_name}' (id={profile.id})")
                profile_map[profile_name] = profile
        db.commit()
    else:
        print("  [!] editor_profiles.json not found, skipping profiles")

    # ── 4. Templates ──
    templates_src = source_dir / "templates"
    templates_dst = settings.templates_dir
    if templates_src.exists():
        for profile_dir in templates_src.iterdir():
            if not profile_dir.is_dir():
                continue
            profile_name = profile_dir.name
            profile = profile_map.get(profile_name) or (
                db.query(Profile).filter(Profile.name == profile_name).first()
            )

            for json_file in profile_dir.glob("*.json"):
                tpl_data = json.loads(json_file.read_text())
                tpl_name = tpl_data.get("name", json_file.stem)

                # Check for existing
                existing = db.query(Template).filter(
                    Template.name == tpl_name,
                    Template.profile_id == (profile.id if profile else None),
                ).first()
                if existing:
                    print(f"  [skip] Template '{tpl_name}'")
                    continue

                # Copy PNG to content-engine templates dir
                png_file = json_file.with_suffix(".png")
                if not png_file.exists():
                    print(f"  [!] Missing PNG for template '{tpl_name}', skipping")
                    continue

                dest_dir = templates_dst / profile_name
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_png = dest_dir / png_file.name
                shutil.copy2(png_file, dest_png)

                video_box = json.dumps(tpl_data.get("box", [0.06, 0.18, 0.94, 0.94]))
                caption_box = json.dumps(tpl_data.get("caption_box", [0.06, 0.08, 0.94, 0.16]))

                tpl = Template(
                    profile_id=profile.id if profile else None,
                    name=tpl_name,
                    image_path=str(dest_png),
                    video_box=video_box,
                    caption_box=caption_box,
                )
                db.add(tpl)
                print(f"  [+] Template '{tpl_name}' → {dest_png.name}")

        db.commit()

        # Set default_template_id on profiles where specified
        for profile_name, info in (json.loads(profiles_path.read_text()) if profiles_path.exists() else {}).items():
            default_tpl_path = info.get("default_template", "")
            if default_tpl_path and profile_name in profile_map:
                tpl_stem = Path(default_tpl_path).stem
                tpl = db.query(Template).filter(
                    Template.name == tpl_stem,
                    Template.profile_id == profile_map[profile_name].id,
                ).first()
                if tpl:
                    profile_map[profile_name].default_template_id = tpl.id
                    print(f"  [=] Profile '{profile_name}' default template → '{tpl_stem}' (id={tpl.id})")
        db.commit()
    else:
        print("  [!] templates/ not found, skipping")

    # ── 5. Videos ──
    downloads_src = source_dir / "downloads"
    if downloads_src.exists():
        count = 0
        for niche_dir in downloads_src.iterdir():
            if not niche_dir.is_dir():
                continue
            niche = db.query(Niche).filter(Niche.name == niche_dir.name).first()
            if not niche:
                # Try partial match
                niche = db.query(Niche).filter(Niche.name.ilike(f"%{niche_dir.name}%")).first()

            for account_dir in niche_dir.iterdir():
                if not account_dir.is_dir():
                    continue
                source_account = account_dir.name

                for mp4 in account_dir.glob("*.mp4"):
                    shortcode = mp4.stem
                    # Check for duplicate
                    existing = db.query(Video).filter(
                        Video.source_account == source_account,
                        Video.shortcode == shortcode,
                    ).first()
                    if existing:
                        continue

                    # Copy to content-engine downloads dir
                    dest_dir = settings.downloads_dir / (niche_dir.name if niche else "unknown") / source_account
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_dir / mp4.name

                    if not dest_file.exists():
                        shutil.copy2(mp4, dest_file)

                    video = Video(
                        platform="instagram",
                        niche_id=niche.id if niche else 1,
                        source_account=source_account,
                        shortcode=shortcode,
                        source_url=f"https://www.instagram.com/reel/{shortcode}/",
                        local_path=str(dest_file),
                        file_bytes=dest_file.stat().st_size,
                        status="downloaded",
                    )
                    db.add(video)
                    count += 1

        db.commit()
        print(f"  [+] Imported {count} videos")
    else:
        print("  [!] downloads/ not found, skipping videos")

    print()
    print("Migration complete!")
    print(f"  Niches:      {db.query(Niche).count()}")
    print(f"  Credentials: {db.query(IGLoginCredential).count()}")
    print(f"  Profiles:    {db.query(Profile).count()}")
    print(f"  Templates:   {db.query(Template).count()}")
    print(f"  Videos:      {db.query(Video).count()}")


def main():
    parser = argparse.ArgumentParser(description="Migrate sm-tester-polished data to content-engine")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / "sm-tester-polished",
        help="Path to sm-tester-polished directory",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Source directory not found: {args.source}")
        sys.exit(1)

    db = SessionLocal()
    try:
        migrate(args.source, db)
    except Exception as e:
        db.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
