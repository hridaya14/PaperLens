import os
from datetime import datetime
from typing import List, Optional

import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")


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


def ask_question(payload: dict):
    response = requests.post(
        f"{API_BASE_URL}/ask",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def get_mindmap(arxiv_id: str):
    response = requests.get(
        f"{API_BASE_URL}/visualization/{arxiv_id}/mindmap",
        timeout=120,  # generation can take 10-30s on first request
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# Flashcard API Functions
# ============================================================================


def get_flashcards(arxiv_id: str, num_cards: int = 15, force_refresh: bool = False):
    """
    Get or generate flashcards for a paper.

    Args:
        arxiv_id: ArXiv ID of the paper
        num_cards: Number of flashcards to generate (5-50)
        force_refresh: Force regeneration even if cached

    Returns:
        Flashcard set with all flashcards and metadata
    """
    params = {
        "num_cards": num_cards,
        "force_refresh": force_refresh,
    }

    response = requests.get(
        f"{API_BASE_URL}/visualization/{arxiv_id}/flashcards",
        params=params,
        timeout=120,  # LLM generation can take time
    )
    response.raise_for_status()
    return response.json()


def get_flashcard_status(arxiv_id: str):
    """Check if flashcards exist and are cached."""
    response = requests.get(
        f"{API_BASE_URL}/visualization/{arxiv_id}/flashcards/status",
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def regenerate_flashcards(arxiv_id: str, num_cards: int = 15):
    """Force regenerate flashcards for a paper."""
    params = {"num_cards": num_cards}

    response = requests.post(
        f"{API_BASE_URL}/visualization/{arxiv_id}/flashcards/regenerate",
        params=params,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()
