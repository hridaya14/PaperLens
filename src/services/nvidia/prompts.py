import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from src.schemas.nvidia import RAGResponse, ResponseMetadata

logger = logging.getLogger(__name__)

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "rag_response",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "Comprehensive answer based on the provided paper excerpts"
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of PDF URLs from papers used in the answer"
                },
                "citations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific arXiv IDs referenced in the answer"
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low", "unknown"],
                            "description": "Confidence level"
                        },
                        "is_partial": {
                            "type": "boolean",
                            "description": "True when the answer is incomplete or partially supported"
                        },
                        "is_unanswerable": {
                            "type": "boolean",
                            "description": "True when the question cannot be answered from provided context"
                        },
                        "diagnostics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Notes for observability about schema fixes or limitations"
                        },
                    },
                    "required": ["confidence", "is_partial", "is_unanswerable", "diagnostics"],
                },
            },
            "required": ["answer", "sources", "metadata"],
        }
    }
}


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
        prompt += (
            "Return ONLY valid JSON that matches the provided schema. "
            "If the context is insufficient to answer, set metadata.is_unanswerable to true "
            "and provide a brief explanation in metadata.diagnostics. "
            "If you can answer but only partially, set metadata.is_partial to true and explain what is missing. "
            "Do not include any prose outside of the JSON object."
        )

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
        diagnostics: List[str] = []
        parsed_json: Optional[Dict[str, Any]] = None
        try:
            # Try to parse as JSON and validate with Pydantic
            parsed_json = json.loads(response)
            validated_response = RAGResponse(**parsed_json)
            return validated_response.model_dump(exclude={"legacy_confidence"})
        except json.JSONDecodeError as e:
            diagnostics.append(f"json_decode_error: {e.msg}")
            logger.warning("Failed to decode LLM response as JSON: %s", e)
        except ValidationError as e:
            diagnostics.append(f"schema_validation_failed: {e.errors()}")
            logger.warning("LLM response failed schema validation: %s", e)

        # Fallback: try to extract JSON from the response
        return ResponseParser._extract_json_fallback(response, diagnostics, parsed_json)

    @staticmethod
    def _extract_json_fallback(
        response: str,
        diagnostics: Optional[List[str]] = None,
        parsed_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Extract JSON from response text as fallback.

        Args:
            response: Raw response text
            diagnostics: Existing diagnostics collected during parsing
            parsed_json: Already parsed JSON if available

        Returns:
            Dictionary with extracted content or fallback
        """
        diag_messages = diagnostics or []

        # Try to find JSON in the response if none was parsed earlier
        if parsed_json is None:
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                try:
                    parsed_json = json.loads(json_match.group())
                except json.JSONDecodeError as e:
                    diag_messages.append(f"fallback_json_decode_error: {e.msg}")

        if parsed_json:
            allowed_keys = {"answer", "sources", "citations", "metadata", "confidence"}
            sanitized = {k: v for k, v in parsed_json.items() if k in allowed_keys}
            extra_keys = sorted(set(parsed_json.keys()) - allowed_keys)
            if extra_keys:
                diag_messages.append(
                    f"stripped_extra_fields: {', '.join(extra_keys)}")

            try:
                validated = RAGResponse(**sanitized)
                if diag_messages:
                    validated.metadata.diagnostics.extend(diag_messages)
                return validated.model_dump(exclude={"legacy_confidence"})
            except ValidationError as e:
                diag_messages.append(f"fallback_validation_failed: {e.errors()}")

        # Final fallback: return response as plain text
        fallback_response = RAGResponse(
            answer=parsed_json.get("answer") if isinstance(parsed_json, dict) and isinstance(parsed_json.get("answer"), str) else response,
            sources=parsed_json.get("sources") if isinstance(parsed_json, dict) and isinstance(parsed_json.get("sources"), list) else [],
            citations=parsed_json.get("citations") if isinstance(parsed_json, dict) and isinstance(parsed_json.get("citations"), list) else [],
            metadata=ResponseMetadata(
                confidence="low",
                is_partial=True,
                is_unanswerable=False,
                diagnostics=diag_messages or [
                    "Used plain-text fallback because schema validation failed"
                ],
            ),
        )
        return fallback_response.model_dump(exclude={"legacy_confidence"})
