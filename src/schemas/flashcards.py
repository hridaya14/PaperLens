from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Flashcard(BaseModel):
    """Internal flashcard representation aligned with DB fields."""

    category: str
    arxiv_id: str
    headline: str
    insight: str
    why_it_matters: Optional[str] = None
    summary_json: dict
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
