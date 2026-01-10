
import os
import requests
from typing import List, Optional
from datetime import datetime

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def search_papers(
    query: Optional[str] = None,
    categories: Optional[List[str]] = None,
    pdf_processed: Optional[bool] = None,
    published_after: Optional[datetime] = None,
    published_before: Optional[datetime] = None,
    limit: int = 20,
    offset: int = 0,
):
    params = {
        "q": query,
        "pdf_processed": pdf_processed,
        "limit": limit,
        "offset": offset,
    }

    if categories:
        params["categories"] = categories
    if published_after:
        params["published_after"] = published_after.isoformat()
    if published_before:
        params["published_before"] = published_before.isoformat()

    response = requests.get(
        f"{API_BASE_URL}/papers/search",
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
