from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ScrapeStartRequest(BaseModel):
    niche_id: int
    credential_id: int
    target_accounts: list[str] = []  # empty = all accounts from niche
    max_reels: int = 10
    min_views: int = 10000
    max_scrolls: int = 15
    scroll_pause_min: float = 1.5
    scroll_pause_max: float = 3.0
    headless: bool = True
    early_stop_dupes: int = 5
    unknown_views_pass: bool = True
    fallback_to_likes: bool = False


class ScrapeJobOut(BaseModel):
    id: int
    niche_id: int
    login_credential_id: int
    status: str
    target_accounts: str
    config_json: str
    results_json: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
