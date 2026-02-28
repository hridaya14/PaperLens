import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from src.exceptions import OllamaException
from src.repositories.flashcards import FlashcardsRepository
from src.services.nvidia.client import NvidiaClient

logger = logging.getLogger(__name__)

DEFAULT_TTL_HOURS = 24


class FlashcardService:
    """Orchestrates flashcard generation and retrieval."""

    def __init__(
        self,
        repo: FlashcardsRepository,
        nvidia_client: NvidiaClient,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        rpm_budget: int = 40,
    ):
        self.repo = repo
        self.nvidia = nvidia_client
        self.ttl = timedelta(hours=ttl_hours)
        self.rpm_budget = rpm_budget

    async def get_cards(
        self, category: str, limit: int = 5, refresh: bool = False
    ) -> tuple[List[dict], bool]:
        """Return flashcards; regenerate if stale/missing or refresh requested.

        :returns: (cards, regenerated_flag)
        """
        fresh_cards = [] if refresh else self.repo.get_fresh(category, limit)
        if len(fresh_cards) >= limit:
            return [self._record_to_dict(c) for c in fresh_cards], False

        cards = await self._regenerate(category, limit)
        return cards, True

    async def _regenerate(self, category: str, limit: int) -> List[dict]:
        """Generate new cards for a category and persist them."""
        candidates = self.repo.get_recent_papers_for_category(
            category, max_candidates=limit * 4
        )

        if not candidates:
            logger.warning(f"No parsed papers found for category {category}")
            return []

        tasks = []
        semaphore = asyncio.Semaphore(self.rpm_budget // 2)  # cushion

        async def summarize(paper):
            async with semaphore:
                return await self._summarize_paper(category, paper)

        for paper in candidates[: limit * 2]:
            tasks.append(asyncio.create_task(summarize(paper)))

        summaries = [s for s in await asyncio.gather(*tasks) if s]
        cards = summaries[:limit]

        expires_at = datetime.now(timezone.utc) + self.ttl
        records = []
        for card in cards:
            card["generated_at"] = datetime.now(timezone.utc)
            card["expires_at"] = expires_at
            summary_copy = self._json_ready(card)
            records.append(
                {
                    "category": category,
                    "arxiv_id": card["arxiv_id"],
                    "headline": card["headline"],
                    "insight": card["insight"],
                    "why_it_matters": card.get("why_it_matters"),
                    "summary_json": summary_copy,
                    "generated_at": card["generated_at"],
                    "expires_at": card["expires_at"],
                }
            )

        if records:
            self.repo.upsert_cards(records)

        return cards

    async def _summarize_paper(self, category: str, paper) -> Optional[dict]:
        """Call NIM to build a flashcard for a single paper."""
        try:
            content = paper.raw_text or paper.abstract or ""
            prompt = self._build_prompt(paper.title, content)
            result = self.nvidia.generate(
                prompt=prompt,
                model=self.nvidia.default_model,
                temperature=0.3,
                top_p=0.9,
                max_tokens=256,
                response_format={
                    "type": "json_object",
                },
            )
            if not result or "response" not in result:
                return None
            parsed = self.nvidia.response_parser.parse_structured_response(
                result["response"]
            )
            raw_answer = parsed.get("answer", "") or ""
            headline = self._extract_headline(raw_answer)
            insight = self._extract_insight(raw_answer, headline)
            why = self._extract_why(parsed, insight, headline)

            return {
                "category": category,
                "arxiv_id": paper.arxiv_id,
                "headline": headline,
                "insight": insight,
                "why_it_matters": why,
                "source_url": paper.pdf_url,
            }
        except OllamaException as e:
            logger.error(f"Flashcard LLM error for {paper.arxiv_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Flashcard generation failed for {paper.arxiv_id}: {e}")
            return None

    def _build_prompt(self, title: str, content: str) -> str:
        """Construct concise prompt for flashcard summary."""
        snippet = content[:1500]
        return (
            "You are summarizing an arXiv paper into a concise flashcard.\n"
            f"Title: {title}\n"
            "Text snippet:\n"
            f"{snippet}\n\n"
            "Return a short headline and 1-2 sentence insight; also a brief 'why it matters'."
        )

    def _extract_headline(self, text: str) -> str:
        cleaned = self._clean_text(text)
        # Take first sentence up to 12 words
        words = cleaned.split()
        headline = " ".join(words[:12]) if words else ""
        return headline or "Research highlight"

    def _extract_insight(self, text: str, headline: str) -> str:
        cleaned = self._clean_text(text)
        if cleaned.lower().startswith(headline.lower()):
            cleaned = cleaned[len(headline):].lstrip(" .-:") or cleaned
        # Limit to first 2 sentences
        parts = cleaned.split(". ")
        insight = ". ".join(parts[:2]).strip()
        return insight or cleaned

    def _extract_why(self, parsed: dict, insight: str, headline: str) -> Optional[str]:
        candidate = parsed.get("why_it_matters") or parsed.get("answer") or ""
        candidate = self._clean_text(candidate)
        if candidate.lower() == insight.lower() or candidate.lower() == headline.lower():
            return None
        return candidate[:240] if candidate else None

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        cleaned = text.replace("**", "").replace("\n", " ").strip()
        for label in ["headline:", "insight:", "why it matters:", "why it matters"]:
            if cleaned.lower().startswith(label):
                cleaned = cleaned[len(label):].strip(" -:")
        return " ".join(cleaned.split())

    def _json_ready(self, obj: dict) -> dict:
        """Remove/convert non-serializable fields before storing in JSONB."""
        out = {}
        for k, v in obj.items():
            if isinstance(v, (datetime,)):
                out[k] = v.isoformat()
            elif isinstance(v, (list, dict, str, int, float, type(None))):
                out[k] = v
            else:
                out[k] = str(v)
        # Drop keys that are purely temporal for the summary blob if desired
        out.pop("generated_at", None)
        out.pop("expires_at", None)
        return out

    def cleanup_expired(self, limit: int = 500) -> int:
        """Delete expired flashcards."""
        return self.repo.delete_expired(limit)

    def _record_to_dict(self, rec) -> dict:
        return {
            "category": rec.category,
            "arxiv_id": rec.arxiv_id,
            "headline": rec.headline,
            "insight": rec.insight,
            "why_it_matters": rec.why_it_matters,
            "generated_at": rec.generated_at,
            "expires_at": rec.expires_at,
            "source_url": rec.summary_json.get("source_url") if rec.summary_json else None,
        }
