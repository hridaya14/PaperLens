import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from src.schemas.nvidia import RAGResponse
from pydantic import BaseModel
from enum import Enum

class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class LLMResponse(BaseModel):
    answer: str
    sources: list[str]
    confidence: Optional[Confidence]
    citations: Optional[list[str]]

class UnstructuredResponse(BaseModel):
    answer: str

class RAGPromptBuilder:
    """Builder class for creating RAG prompts."""

    def __init__(self):
        """Initialize the prompt builder."""
        self.prompts_dir = Path(__file__).parent / "prompts"
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the system prompt from the text file.

        Returns:
            System prompt string
        """
        prompt_file = self.prompts_dir / "rag_system.txt"
        if not prompt_file.exists():
            # Fallback to default prompt if file doesn't exist
            return (
                "You are an AI assistant specialized in answering questions about "
                "academic papers from arXiv. Base your answer STRICTLY on the provided "
                "paper excerpts."
            )
        return prompt_file.read_text().strip()

    def create_rag_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Create a RAG prompt with query and retrieved chunks.

        Args:
            query: User's question
            chunks: List of retrieved chunks with metadata from OpenSearch

        Returns:
            Formatted prompt string
        """
        prompt = f"{self.system_prompt}\n\n"
        prompt += "### Context from Papers (do NOT imitate formatting):\n\n"

        for i, chunk in enumerate(chunks, 1):
            # Get the actual chunk text
            chunk_text = chunk.get("chunk_text", chunk.get("content", ""))
            arxiv_id = chunk.get("arxiv_id", "")

            prompt += f"[Source {i} — arXiv:{arxiv_id}]\n"
            prompt += "```text\n"
            prompt += f"{chunk_text}\n"
            prompt += "```\n\n"

        prompt += f"### Question:\n{query}\n\n"
        prompt += "### Answer (cite sources using [arXiv:id] format):\n"

        return prompt

    def create_structured_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a prompt for Ollama with structured output format.

        Args:
            query: User's question
            chunks: List of retrieved chunks

        Returns:
            Dictionary with prompt and format schema for Ollama
        """
        prompt_text = self.create_rag_prompt(query, chunks)

        # Return prompt with Pydantic model schema for structured output
        return {
            "prompt": prompt_text,
            "format": RAGResponse.model_json_schema(),
        }

class MindMapPromptBuilder:
    """Builds prompts for mind map generation from paper chunks."""

    _SKIP_SECTIONS = {
        "references", "bibliography", "acknowledgements",
        "acknowledgments", "appendix", "author contributions",
        "conflict of interest", "funding", "disclosure",
    }

    def __init__(self, max_chars: int = 32_000):
        self._max_chars = max_chars
        self.prompts_dir = Path(__file__).parent / "prompts"
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the system prompt from the text file.

        Returns:
            System prompt string
        """
        prompt_file = self.prompts_dir / "mindmap.txt"
        if not prompt_file.exists():
            # Fallback to default prompt if file doesn't exist
            return (
                "You are an AI assistant specialized in answering questions about "
                "academic papers from arXiv. Base your answer STRICTLY on the provided "
                "paper excerpts."
            )
        return prompt_file.read_text().strip()

    def build_prompt(
        self,
        paper_title: str,
        arxiv_id: str,
        chunks: list,   # list[TextChunk]
    ) -> str:
        sections = self._assemble_sections(chunks)
        sections_block = "\n\n".join(
            f"### {title or 'General'}\n{text}"
            for title, text in sections
        )
        return (
            f"{self.system_prompt}\n\n"
            f"Paper Title: {paper_title}\n"
            f"ArXiv ID: {arxiv_id}\n\n"
            f"Paper Content:\n{sections_block}\n\n"
            f"Generate the conceptual mind map JSON now:"
        )

    def _assemble_sections(self, chunks: list) -> list[tuple[str | None, str]]:
        from collections import defaultdict

        def get_chunk_index(c):
            return c["chunk_index"] if isinstance(c, dict) else c.metadata.chunk_index

        def get_section_title(c):
            return c.get("section_title") if isinstance(c, dict) else c.metadata.section_title

        def get_text(c):
            return c.get("text", c.get("chunk_text", "")) if isinstance(c, dict) else c.text

        sorted_chunks = sorted(chunks, key=get_chunk_index)

        section_order: list[str] = []
        section_texts: dict[str, list[str]] = defaultdict(list)

        for chunk in sorted_chunks:
            section = (get_section_title(chunk) or "").strip()
            if section.lower() in self._SKIP_SECTIONS:
                continue
            key = section or "_unknown"
            if key not in section_texts:
                section_order.append(key)
            section_texts[key].append(get_text(chunk))

        sections: list[tuple[str | None, str]] = []
        total_chars = 0

        for key in section_order:
            text = " ".join(section_texts[key])
            if total_chars + len(text) > self._max_chars:
                remaining = self._max_chars - total_chars
                if remaining > 200:
                    text = text[:remaining] + "..."
                    sections.append((key if key != "_unknown" else None, text))
                break
            sections.append((key if key != "_unknown" else None, text))
            total_chars += len(text)

        return sections


class ResponseParser:
    """Parser for LLM responses."""

    @staticmethod
    def parse_structured_response(response: str) -> Dict[str, Any]:
        """Parse a structured response from Ollama.

        Args:
            response: Raw LLM response string

        Returns:
            Dictionary with parsed response
        """
        try:
            # Try to parse as JSON and validate with Pydantic
            parsed_json = json.loads(response)
            validated_response = RAGResponse(**parsed_json)
            return validated_response.model_dump()
        except (json.JSONDecodeError, ValidationError):
            # Fallback: try to extract JSON from the response
            return ResponseParser._extract_json_fallback(response)

    @staticmethod
    def _extract_json_fallback(response: str) -> Dict[str, Any]:
        """Extract JSON from response text as fallback.

        Args:
            response: Raw response text

        Returns:
            Dictionary with extracted content or fallback
        """
        # Try to find JSON in the response
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # Validate with Pydantic, using defaults for missing fields
                validated = RAGResponse(**parsed)
                return validated.model_dump()
            except (json.JSONDecodeError, ValidationError):
                pass

        # Final fallback: return response as plain text
        return {
            "answer": response,
            "sources": [],
            "confidence": "low",
            "citations": [],
        }
