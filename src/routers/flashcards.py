import logging
from fastapi import APIRouter, HTTPException, Query

from src.dependencies import FlashcardsServiceDep
from src.schemas.api.flashcards import FlashcardsQuery, FlashcardsResponse, FlashcardDTO

router = APIRouter(prefix="/flashcards", tags=["flashcards"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=FlashcardsResponse)
async def get_flashcards(
    category: str = Query(..., description="arXiv category code, e.g., cs.AI"),
    limit: int = Query(5, ge=1, le=10),
    refresh: bool = Query(False, description="Force regeneration"),
    service: FlashcardsServiceDep = None,
):
    """Return flashcards for a category, generating if needed."""
    try:
        cards, regenerated = await service.get_cards(
            category=category, limit=limit, refresh=refresh
        )

        stale = False
        if cards:
            stale = any(card.get("expires_at") and card["expires_at"] <= cards[0].get("generated_at") for card in cards)

        dto_cards = [
            FlashcardDTO(
                category=card["category"],
                arxiv_id=card["arxiv_id"],
                headline=card["headline"],
                insight=card["insight"],
                why_it_matters=card.get("why_it_matters"),
                generated_at=card.get("generated_at"),
                expires_at=card.get("expires_at"),
                source_url=card.get("source_url"),
            )
            for card in cards
        ]

        return FlashcardsResponse(
            category=category,
            cards=dto_cards,
            stale=stale,
            regenerated=regenerated,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch flashcards: {e}")
        raise HTTPException(status_code=500, detail="Unable to fetch flashcards")


@router.delete("/expired", response_model=dict)
def cleanup_expired(
    limit: int = Query(500, ge=1, le=5000),
    service: FlashcardsServiceDep = None,
):
    """Best-effort cleanup of expired flashcards."""
    try:
        deleted = service.cleanup_expired(limit=limit)
        return {"deleted": deleted}
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail="Cleanup failed")
