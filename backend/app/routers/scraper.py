import asyncio
import json
import queue as thread_queue
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.scrape import ScrapeJob
from app.schemas.scraper import ScrapeJobOut, ScrapeStartRequest
from app.services.scraper_service import (
    SENTINEL,
    get_log_queue,
    run_scrape_job,
)

router = APIRouter()
ws_router = APIRouter()


@router.post("/start", response_model=ScrapeJobOut, status_code=201)
async def start_scrape(body: ScrapeStartRequest, network_id: int | None = None, db: Session = Depends(get_db)):
    config = body.model_dump()
    job = ScrapeJob(
        niche_id=body.niche_id,
        login_credential_id=body.credential_id,
        status="pending",
        config_json=json.dumps(config),
        target_accounts=json.dumps(body.target_accounts),
        network_id=network_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Start scraper in background thread
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None,
        partial(
            run_scrape_job,
            job_id=job.id,
            niche_id=body.niche_id,
            credential_id=body.credential_id,
            target_accounts=body.target_accounts,
            max_reels=body.max_reels,
            min_views=body.min_views,
            max_scrolls=body.max_scrolls,
            scroll_pause=(body.scroll_pause_min, body.scroll_pause_max),
            headless=body.headless,
            early_stop_dupes=body.early_stop_dupes,
            unknown_views_pass=body.unknown_views_pass,
            fallback_to_likes=body.fallback_to_likes,
        ),
    )

    return job


@router.get("/jobs", response_model=list[ScrapeJobOut])
def list_jobs(limit: int = 20, network_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(ScrapeJob)
    if network_id is not None:
        q = q.filter(ScrapeJob.network_id == network_id)
    return q.order_by(ScrapeJob.created_at.desc()).limit(limit).all()


@router.get("/jobs/{job_id}", response_model=ScrapeJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@ws_router.websocket("/{job_id}")
async def scraper_websocket(websocket: WebSocket, job_id: int):
    await websocket.accept()
    q = get_log_queue(job_id)

    try:
        while True:
            try:
                msg = await asyncio.to_thread(q.get, timeout=1.0)
            except thread_queue.Empty:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break
                continue

            if msg is SENTINEL:
                await websocket.send_json({"type": "complete"})
                break

            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
