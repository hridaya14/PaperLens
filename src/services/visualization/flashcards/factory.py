"""
Factory for flashcard service dependency injection.

Follows the same pattern as mindmap factory.

Location: src/services/visualization/flashcards/factory.py
"""

from src.database import get_db_session
from src.db.redis.redis import get_redis_client
from src.repositories.flashcards import FlashcardRepository
from src.services.nvidia.factory import make_nvidia_client
from src.services.visualization.flashcards.cache import FlashcardCache
from src.services.visualization.flashcards.client import FlashcardService
from src.services.visualization.flashcards.generator import FlashcardGenerator


def get_flashcard_service() -> FlashcardService:
    """
    Create and configure FlashcardService with all dependencies.

    Dependencies:
    - FlashcardGenerator (needs NvidiaClient)
    - FlashcardCache (needs Redis)
    - FlashcardRepository (needs DB session)

    Returns:
        Fully configured FlashcardService
    """
    # Initialize LLM client
    nvidia_client = make_nvidia_client()

    # Initialize generator
    generator = FlashcardGenerator(nvidia_client=nvidia_client)

    # Initialize Redis cache
    redis_client = get_redis_client()
    cache = FlashcardCache(redis_client=redis_client)

    # Initialize repository
    # Note: This creates a new DB session
    # For FastAPI endpoints, you'll want to use dependency injection instead
    db_session = get_db_session()
    repository = FlashcardRepository(session=db_session)

    # Assemble service
    return FlashcardService(
        generator=generator,
        cache=cache,
        repository=repository,
    )


def get_flashcard_service_with_db(db_session) -> FlashcardService:
    """
    Create FlashcardService with provided DB session.

    Use this in FastAPI endpoints with dependency injection:

    ```python
    @router.get("/flashcards/{paper_id}")
    async def get_flashcards(
        paper_id: str,
        db: Session = Depends(get_db),
    ):
        service = get_flashcard_service_with_db(db)
        return await service.get_or_generate(...)
    ```

    Args:
        db_session: SQLAlchemy Session from FastAPI dependency

    Returns:
        FlashcardService configured with provided session
    """
    nvidia_client = make_nvidia_client()
    generator = FlashcardGenerator(nvidia_client=nvidia_client)

    redis_client = get_redis_client()
    cache = FlashcardCache(redis_client=redis_client)

    repository = FlashcardRepository(session=db_session)

    return FlashcardService(
        generator=generator,
        cache=cache,
        repository=repository,
    )
