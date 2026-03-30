#!/usr/bin/env python3
"""
Local Media Server for Content Engine.

Run this on your machine so the live site can load thumbnails and stream
videos from your shared Google Drive folder.

Usage:
    python media_server.py                        # auto-detects Google Drive
    python media_server.py --port 8200            # custom port
    python media_server.py --media-root /path/to  # custom media root

Then set "http://localhost:8100" as your Local Media Server URL in Settings.
"""

import argparse
import ipaddress
import os
import sys
from pathlib import Path

# Auto-detect Google Drive media folder
def find_gdrive_media():
    cloud_storage = Path.home() / "Library" / "CloudStorage"
    if not cloud_storage.exists():
        # Windows
        cloud_storage = Path.home() / "Google Drive"
        if not cloud_storage.exists():
            cloud_storage = Path(os.environ.get("GOOGLE_DRIVE_PATH", ""))

    if cloud_storage.exists():
        for d in cloud_storage.iterdir():
            if d.name.startswith("GoogleDrive"):
                media = d / "My Drive" / "content-engine-media"
                if media.exists():
                    return media

    # Windows: check common paths
    for base in [Path.home() / "Google Drive" / "My Drive", Path.home() / "Google Drive"]:
        media = base / "content-engine-media"
        if media.exists():
            return media

    return None


parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8100)
parser.add_argument("--media-root", type=str, default=None)
args = parser.parse_args()

# Set MEDIA_ROOT before importing app config
media_root = args.media_root
if not media_root:
    gdrive = find_gdrive_media()
    if gdrive:
        media_root = str(gdrive)
        print(f"  Found Google Drive media: {gdrive}")
    else:
        media_root = str(Path(__file__).parent)
        print(f"  No Google Drive found, using local: {media_root}")

os.environ["MEDIA_ROOT"] = media_root

import uvicorn
from app.config import settings
from app.database import Base, engine

Base.metadata.create_all(bind=engine)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import videos

app = FastAPI(title="Content Engine - Local Media Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(videos.router, prefix="/api/videos", tags=["videos"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "local-media", "media_root": media_root}


if __name__ == "__main__":
    # Generate self-signed cert for HTTPS (needed when live HTTPS site loads from localhost)
    import ssl
    import tempfile
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256())
        )

        cert_file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
        cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
        cert_file.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        cert_file.close()

        print(f"\n  Local Media Server on https://localhost:{args.port}")
        print(f"  Media root: {media_root}")
        print(f"  Set https://localhost:{args.port} in Settings → Local Media Server")
        print(f"  NOTE: First visit https://localhost:{args.port}/api/health in your browser and accept the certificate\n")
        uvicorn.run(app, host="0.0.0.0", port=args.port, ssl_certfile=cert_file.name, ssl_keyfile=cert_file.name)
    except Exception as e:
        print(f"  Could not create HTTPS cert ({e}), falling back to HTTP")
        print(f"\n  Local Media Server on http://localhost:{args.port}")
        print(f"  Media root: {media_root}")
        print(f"  NOTE: HTTP only works with localhost:5173, not the live HTTPS site\n")
        uvicorn.run(app, host="0.0.0.0", port=args.port)
