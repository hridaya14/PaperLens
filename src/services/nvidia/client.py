import json
import logging
import time
import traceback
from typing import Any, Dict, Generator, List, Optional

from openai import APIConnectionError, APITimeoutError, OpenAI, OpenAIError
from src.config import get_settings
from src.exceptions import OllamaConnectionError, OllamaException, OllamaTimeoutError
from src.schemas.nvidia import RAGResponse
from src.services.nvidia.prompts import (
    FlashcardPromptBuilder,
    MindMapPromptBuilder,
    RAGPromptBuilder,
    ResponseParser,
)

logger = logging.getLogger(__name__)


class NvidiaClient:
    """Client for OpenAI-compatible LLMs (NVIDIA / local / LM Studio)."""

    def __init__(self):
        settings = get_settings()

        api_key = settings.nvidia_api_key if settings.llm_mode == "nvidia" else settings.local_llm_api_key
        base_url = settings.nvidia_base_url if settings.llm_mode == "nvidia" else settings.local_llm_server

        self.client = OpenAI(api_key=api_key, base_url=base_url)

        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()
        self.mindmap_prompt_builder = MindMapPromptBuilder()
        self.flashcard_prompt_builder = FlashcardPromptBuilder()

        self.timeout = float(settings.nvidia_timeout)

        self.default_model = "meta/llama-3.3-70b-instruct" if settings.llm_mode == "nvidia" else "qwen/qwen3.5-9b"

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    def _extract_usage(self, completion):
        usage = getattr(completion, "usage", None)
        if usage:
            return (
                getattr(usage, "prompt_tokens", None),
                getattr(usage, "completion_tokens", None),
            )
        return None, None

    # ─────────────────────────────────────────────
    # Health
    # ─────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        try:
            models = self.client.models.list()
            return {
                "status": "healthy",
                "model_count": len(models.data),
            }
        except APIConnectionError as e:
            raise OllamaConnectionError(f"Cannot connect to LLM service: {e}") from e
        except APITimeoutError as e:
            raise OllamaTimeoutError(f"LLM service timeout: {e}") from e
        except Exception as e:
            raise OllamaException(f"Health check failed: {e}") from e

    # ─────────────────────────────────────────────
    # NON-STREAMING GENERATION
    # ─────────────────────────────────────────────

    def generate(
        self,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        stream: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            if stream:
                raise OllamaException("Use generate_stream() for streaming")

            model = model or self.default_model

            t0 = time.perf_counter()

            completion = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                top_p=kwargs.get("top_p", 0.9),
                max_tokens=kwargs.get("max_tokens", 2048),
            )

            t1 = time.perf_counter()

            duration_s = t1 - t0
            total_ms = duration_s * 1000

            text = completion.choices[0].message.content

            input_tokens, output_tokens = self._extract_usage(completion)

            if output_tokens is None:
                output_tokens = self._estimate_tokens(text)

            tokens_per_sec = output_tokens / duration_s if output_tokens and duration_s > 0 else None

            return {
                "response": text,
                "metrics": {
                    "total_ms": total_ms,
                    "llm_ms": total_ms,
                    "ttft_ms": None,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "tokens_per_sec": tokens_per_sec,
                },
            }

        except APIConnectionError as e:
            raise OllamaConnectionError(f"Cannot connect to LLM: {e}")
        except APITimeoutError as e:
            raise OllamaTimeoutError(f"LLM request timeout: {e}")
        except OpenAIError as e:
            raise OllamaException(f"LLM API error: {e}")
        except Exception as e:
            raise OllamaException(f"Generation failed: {e}")

    # ─────────────────────────────────────────────
    # STREAMING GENERATION (TTFT + TPS)
    # ─────────────────────────────────────────────

    def generate_stream(
        self,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> Generator[Dict[str, Any], None, None]:
        try:
            model = model or self.default_model

            t0 = time.perf_counter()
            first_token_time = None
            output_tokens = 0

            stream = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                top_p=kwargs.get("top_p", 0.9),
                max_tokens=kwargs.get("max_tokens", 2048),
                stream=True,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue

                if first_token_time is None:
                    first_token_time = time.perf_counter()

                output_tokens += self._estimate_tokens(delta)
                yield {"response": delta, "metrics": None}

            t1 = time.perf_counter()
            duration_s = t1 - t0
            ttft_ms = (first_token_time - t0) * 1000 if first_token_time else None
            tokens_per_sec = output_tokens / duration_s if output_tokens and duration_s > 0 else None

            yield {
                "response": None,
                "metrics": {
                    "total_ms": duration_s * 1000,
                    "llm_ms": duration_s * 1000,
                    "ttft_ms": ttft_ms,
                    "input_tokens": None,
                    "output_tokens": output_tokens,
                    "tokens_per_sec": tokens_per_sec,
                },
            }

        except APIConnectionError as e:
            raise OllamaConnectionError(f"Cannot connect to LLM stream: {e}")
        except APITimeoutError as e:
            raise OllamaTimeoutError(f"Streaming timeout: {e}")
        except Exception as e:
            raise OllamaException(f"Streaming failed: {e}")

    # ─────────────────────────────────────────────
    # RAG (NON-STREAMING)
    # ─────────────────────────────────────────────

    def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a RAG answer using plain-text generation.

        Structured output (response_format JSON schema) was removed — constrained
        decoding validates every token against the schema, adding significant
        latency with no benefit over parsing the plain text response.
        """
        try:
            model = model or self.default_model

            # Use the same plain prompt as the streaming path for consistency.
            # create_rag_prompt instructs the model to respond in JSON naturally,
            # which the response_parser already handles.
            prompt = self.prompt_builder.create_rag_prompt(query, chunks)

            response = self.generate(
                model=model,
                prompt=prompt,
                temperature=0.7,
                top_p=0.9,
            )

            raw_response = response["response"]
            metrics = response.get("metrics") or {}

            parsed_response = self.response_parser.parse_structured_response(raw_response)

            if metrics:
                parsed_response["metrics"] = metrics

            # Ensure sources
            if not parsed_response.get("sources"):
                seen, sources = set(), []
                for chunk in chunks:
                    arxiv_id = chunk.get("arxiv_id")
                    if arxiv_id:
                        clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
                        pdf_url = f"https://arxiv.org/pdf/{clean_id}"
                        if pdf_url not in seen:
                            sources.append(pdf_url)
                            seen.add(pdf_url)
                parsed_response["sources"] = sources

            # Ensure citations
            if not parsed_response.get("citations"):
                citations = list(set(chunk.get("arxiv_id") for chunk in chunks if chunk.get("arxiv_id")))
                parsed_response["citations"] = citations[:5]

            return parsed_response

        except Exception as e:
            logger.error(f"Error generating RAG answer: {e}")
            raise OllamaException(f"Failed to generate RAG answer: {e}")

    # ─────────────────────────────────────────────
    # STREAMING RAG
    # ─────────────────────────────────────────────

    def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        try:
            model = model or self.default_model
            prompt = self.prompt_builder.create_rag_prompt(query, chunks)

            yield from self.generate_stream(
                model=model,
                prompt=prompt,
                temperature=0.7,
                top_p=0.9,
            )

        except Exception as e:
            logger.error(f"Error generating streaming RAG answer: {e}")
            raise OllamaException(f"Streaming RAG failed: {e}")

    # -----------------------------------------------
    # Visualization utils
    # -----------------------------------------------
    def generate_mindmap(self, paper_title, arxiv_id, chunks, model=None):
        try:
            model = model or self.default_model

            prompt = self.mindmap_prompt_builder.build_prompt(
                paper_title=paper_title,
                arxiv_id=arxiv_id,
                chunks=chunks,
            )

            # Call completions directly without UnstructuredResponse wrapper
            # so the LLM outputs raw JSON without being forced into {"answer": "..."}
            completion = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                top_p=0.9,
                max_tokens=4096,
            )

            raw_text = completion.choices[0].message.content

            if not raw_text:
                raise OllamaException("Empty response from LLM")

            return {"raw": raw_text}

        except OllamaConnectionError:
            raise
        except OllamaTimeoutError:
            raise
        except OllamaException:
            raise
        except Exception as e:
            logger.error(f"Error generating mind map: {e}")
            raise OllamaException(f"Failed to generate mind map: {e}")

    def generate_flashcards(
        self,
        paper_title: str,
        paper_abstract: str,
        chunks: list,
        num_cards: int = 15,
        topics: list[str] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate study flashcards for a research paper.

        Args:
            paper_title: Title of the paper
            paper_abstract: Abstract text
            chunks: List of text chunks from the paper
            num_cards: Number of flashcards to generate (default: 15)
            topics: Optional list of topics to focus on
            model: Optional model override

        Returns:
            {"raw": str} - Raw JSON string from LLM

        Raises:
            OllamaConnectionError: If connection to LLM fails
            OllamaTimeoutError: If request times out
            OllamaException: For other LLM errors
        """
        try:
            model = model or self.default_model

            # Build the prompt using FlashcardPromptBuilder
            # Note: Initialize flashcard_prompt_builder in __init__ like mindmap_prompt_builder
            prompt = self.flashcard_prompt_builder.build_prompt(
                paper_title=paper_title,
                paper_abstract=paper_abstract,
                chunks=chunks,
                num_cards=num_cards,
                topics=topics,
            )

            completion = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Lower temperature for more consistent flashcards
                top_p=0.9,
                max_tokens=4096,
            )

            raw_text = completion.choices[0].message.content

            if not raw_text:
                raise OllamaException("Empty response from LLM")

            return {"raw": raw_text}

        except OllamaConnectionError:
            raise
        except OllamaTimeoutError:
            raise
        except OllamaException:
            raise
        except Exception as e:
            logger.error(f"Error generating flashcards: {e}")
            raise OllamaException(f"Failed to generate flashcards: {e}")
