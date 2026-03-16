import json
import logging
from datetime import datetime, timezone

from src.schemas.visualization.mindmaps import MindMap, MindMapNode
from src.services.nvidia.client import NvidiaClient
from src.config import get_settings
from src.exceptions import OllamaConnectionError, OllamaTimeoutError, OllamaException

logger = logging.getLogger(__name__)
settings = get_settings()


class MindMapGenerationError(Exception):
    pass


class MindMapGenerator:
    def __init__(self, nvidia_client: NvidiaClient):
        self._client = nvidia_client

    async def generate(self, paper_id: str, arxiv_id: str, paper_title: str, chunks: list) -> MindMap:
        if not chunks:
            raise MindMapGenerationError(f"No chunks found for paper_id={paper_id}")

        logger.info("Generating mind map", extra={"paper_id": paper_id, "chunk_count": len(chunks)})

        try:
            result = self._client.generate_mindmap(
                paper_title=paper_title,
                arxiv_id=arxiv_id,
                chunks=chunks,
            )
        except OllamaConnectionError as e:
            raise MindMapGenerationError(f"LLM connection failed: {e}") from e
        except OllamaTimeoutError as e:
            raise MindMapGenerationError(f"LLM timed out: {e}") from e
        except OllamaException as e:
            raise MindMapGenerationError(f"LLM error: {e}") from e

        return self._parse(result["raw"], paper_id, arxiv_id, paper_title)

    def _parse(self, raw: str, paper_id: str, arxiv_id: str, paper_title: str) -> MindMap:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from LLM", extra={"preview": cleaned[:300]})
            raise MindMapGenerationError(f"LLM returned invalid JSON: {e}") from e

        try:
            root_node = MindMapNode.model_validate(data["root"])
        except Exception as e:
            raise MindMapGenerationError(f"Mind map validation failed: {e}") from e

        return MindMap(
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            paper_title=data.get("paper_title", paper_title),
            root=root_node,
            sections_covered=data.get("sections_covered", []),
            generated_at=datetime.now(timezone.utc),
            model_used=settings.nvidia_model if hasattr(settings, "nvidia_model") else "meta/llama-3.3-70b-instruct",
        )
