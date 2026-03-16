"""
Flashcard generator service.

Orchestrates flashcard generation from paper content using LLM.
Follows the same pattern as MindMapGenerator.

Location: src/services/visualization/flashcards/generator.py
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from src.config import get_settings
from src.exceptions import OllamaConnectionError, OllamaException, OllamaTimeoutError
from src.schemas.visualization.flashcards import (
    Flashcard,
    FlashcardContent,
    FlashcardGenerationInput,
    FlashcardGenerationOutput,
    FlashcardSet,
)
from src.services.nvidia.client import NvidiaClient

logger = logging.getLogger(__name__)
settings = get_settings()


class FlashcardGenerationError(Exception):
    """Raised when flashcard generation fails."""

    pass


class FlashcardGenerator:
    """Generator for creating study flashcards from research papers."""

    def __init__(self, nvidia_client: NvidiaClient):
        self._client = nvidia_client

    async def generate(
        self,
        paper_id: str,
        arxiv_id: Optional[str],
        paper_title: str,
        paper_abstract: str,
        chunks: list,
        num_cards: int = 15,
        topics: Optional[List[str]] = None,
    ) -> FlashcardSet:
        """
        Generate a complete flashcard set for a paper.

        Args:
            paper_id: UUID of the paper
            arxiv_id: ArXiv ID (optional)
            paper_title: Title of the paper
            paper_abstract: Abstract text
            chunks: List of text chunks from OpenSearch
            num_cards: Number of flashcards to generate
            topics: Optional list of topics to focus on

        Returns:
            FlashcardSet with all generated flashcards

        Raises:
            FlashcardGenerationError: If generation fails
        """
        if not chunks:
            raise FlashcardGenerationError(f"No chunks found for paper_id={paper_id}")

        logger.info("Generating flashcards", extra={"paper_id": paper_id, "chunk_count": len(chunks), "num_cards": num_cards})

        try:
            # Call LLM to generate flashcards
            result = self._client.generate_flashcards(
                paper_title=paper_title,
                paper_abstract=paper_abstract,
                chunks=chunks,
                num_cards=num_cards,
                topics=topics,
            )
        except OllamaConnectionError as e:
            raise FlashcardGenerationError(f"LLM connection failed: {e}") from e
        except OllamaTimeoutError as e:
            raise FlashcardGenerationError(f"LLM timed out: {e}") from e
        except OllamaException as e:
            raise FlashcardGenerationError(f"LLM error: {e}") from e

        # Parse the raw JSON response
        flashcard_set = self._parse(
            raw=result["raw"],
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            paper_title=paper_title,
            num_cards=num_cards,
        )

        logger.info(
            "Flashcards generated successfully", extra={"paper_id": paper_id, "cards_generated": len(flashcard_set.flashcards)}
        )

        return flashcard_set

    def _parse(
        self,
        raw: str,
        paper_id: str,
        arxiv_id: Optional[str],
        paper_title: str,
        num_cards: int,
    ) -> FlashcardSet:
        """
        Parse LLM output into validated FlashcardSet.

        Args:
            raw: Raw JSON string from LLM
            paper_id: Paper UUID
            arxiv_id: ArXiv ID
            paper_title: Paper title
            num_cards: Expected number of cards

        Returns:
            Validated FlashcardSet

        Raises:
            FlashcardGenerationError: If parsing fails
        """
        # Clean up potential markdown code blocks
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            # Remove first line (```json or ```) and last line (```)
            cleaned = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from LLM", extra={"preview": cleaned[:300]})
            raise FlashcardGenerationError(f"LLM returned invalid JSON: {e}") from e

        # Validate the flashcards array exists
        if "flashcards" not in data or not isinstance(data["flashcards"], list):
            raise FlashcardGenerationError("LLM response missing 'flashcards' array")

        # Parse each flashcard
        flashcards: List[Flashcard] = []
        now = datetime.now(timezone.utc)

        for idx, card_data in enumerate(data["flashcards"]):
            try:
                # Validate flashcard content
                content = FlashcardContent(
                    front=card_data.get("front", ""),
                    back=card_data.get("back", ""),
                    topic=card_data.get("topic"),
                    difficulty=card_data.get("difficulty"),
                )

                # Create flashcard with index
                flashcard = Flashcard(
                    paper_id=paper_id,
                    front=content.front,
                    back=content.back,
                    topic=content.topic,
                    difficulty=content.difficulty,
                    card_index=idx,
                    generated_at=now,
                )

                flashcards.append(flashcard)

            except Exception as e:
                logger.warning(f"Skipping invalid flashcard at index {idx}: {e}", extra={"card_data": card_data})
                continue

        # Ensure we have at least some flashcards
        if not flashcards:
            raise FlashcardGenerationError("No valid flashcards generated from LLM response")

        # Warn if we got fewer cards than requested
        if len(flashcards) < num_cards * 0.7:  # Allow 30% tolerance
            logger.warning(f"Generated {len(flashcards)} flashcards, expected {num_cards}")

        # Build complete flashcard set
        from datetime import timedelta

        flashcard_set = FlashcardSet(
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            paper_title=paper_title,
            flashcards=flashcards,
            total_cards=len(flashcards),
            generated_at=now,
            expires_at=now + timedelta(days=7),  # 7-day TTL
            model_used=settings.nvidia_model if hasattr(settings, "nvidia_model") else "meta/llama-3.3-70b-instruct",
        )

        return flashcard_set
