import json
import logging
from typing import Any, Dict, List, Optional, Generator

from openai import OpenAI, APIConnectionError, APITimeoutError, OpenAIError

from src.config import get_settings
from src.exceptions import OllamaConnectionError, OllamaException, OllamaTimeoutError
from src.schemas.nvidia import RAGResponse
from src.services.nvidia.prompts import RAGPromptBuilder, ResponseParser
import traceback

logger = logging.getLogger(__name__)


class NvidiaClient:
    """Client for NVIDIA-hosted OpenAI-compatible API (meta/llama-3.3-70b-instruct)."""

    def __init__(self):
        """Initialize OpenAI client with NVIDIA endpoint and API key."""
        settings = get_settings()
        self.client = OpenAI(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url
        )
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()
        self.timeout = float(settings.nvidia_timeout)
        self.default_model = "meta/llama-3.3-70b-instruct"

    def health_check(self) -> Dict[str, Any]:
        """Check if NVIDIA LLM endpoint is reachable."""
        try:
            logger.info("Performing NVIDIA LLM health check...")
            models = self.client.models.list()
            logger.info(f"NVIDIA LLM endpoint reachable — {
                        len(models.data)} models found.")
            return {
                "status": "healthy",
                "message": "NVIDIA LLM endpoint reachable",
                "model_count": len(models.data),
            }

        except APIConnectionError as e:
            tb = traceback.format_exc()
            logger.error(
                f"[LLM ERROR] Connection to NVIDIA API failed.\n"
                f"Base URL: {self.client.base_url}\n"
                f"Exception Type: {type(e).__name__}\n"
                f"Details: {e}\n"
                f"Traceback:\n{tb}"
            )
            raise OllamaConnectionError(
                f"Cannot connect to LLM service: {e}") from e

        except APITimeoutError as e:
            tb = traceback.format_exc()
            logger.error(
                f"[LLM ERROR] NVIDIA API timeout.\n"
                f"Base URL: {self.client.base_url}\n"
                f"Timeout: {self.timeout}s\n"
                f"Details: {e}\n"
                f"Traceback:\n{tb}"
            )
            raise OllamaTimeoutError(f"LLM service timeout: {e}") from e

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(
                f"[LLM ERROR] Unexpected failure during NVIDIA health check.\n"
                f"Base URL: {self.client.base_url}\n"
                f"Exception Type: {type(e).__name__}\n"
                f"Details: {e}\n"
                f"Traceback:\n{tb}"
            )
            raise OllamaException(f"Health check failed: {e}") from e

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        try:
            response = self.client.models.list()
            return [{"id": m.id, "created": m.created, "owned_by": m.owned_by} for m in response.data]
        except Exception as e:
            raise OllamaException(f"Error listing models: {e}")

    def generate(
        self,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        stream: bool = False,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Generate text using the specified model."""
        try:
            model = model or self.default_model
            logger.info(f"Sending request to LLM: model={
                        model}, stream={stream}")

            if stream:
                raise OllamaException(
                    "Use generate_stream() for streaming responses")

            completion = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                top_p=kwargs.get("top_p", 0.9),
                max_tokens=kwargs.get("max_tokens", 2048),
                response_format=kwargs.get("response_format"),
            )

            return {"response": completion.choices[0].message.content}

        except APIConnectionError as e:
            raise OllamaConnectionError(f"Cannot connect to LLM: {e}")
        except APITimeoutError as e:
            raise OllamaTimeoutError(f"LLM request timeout: {e}")
        except OpenAIError as e:
            raise OllamaException(f"LLM API error: {e}")
        except Exception as e:
            raise OllamaException(f"Generation failed: {e}")

    def generate_stream(
        self,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream generation results incrementally."""
        try:
            model = model or self.default_model
            logger.info(f"Starting streaming generation: model={model}")

            with self.client.chat.completions.stream(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                top_p=kwargs.get("top_p", 0.9),
                max_tokens=kwargs.get("max_tokens", 2048),
            ) as stream:
                for event in stream:
                    if event.type == "message":
                        yield {"response": event.message["content"]}
                    elif event.type == "error":
                        logger.error(f"Stream error: {event.error}")
                        raise OllamaException(event.error)

        except APIConnectionError as e:
            raise OllamaConnectionError(f"Cannot connect to LLM stream: {e}")
        except APITimeoutError as e:
            raise OllamaTimeoutError(f"LLM streaming timeout: {e}")
        except Exception as e:
            raise OllamaException(f"Streaming generation failed: {e}")

    def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: Optional[str] = None,
        use_structured_output: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate a RAG answer using retrieved chunks, with schema-based structured output.
        """
        try:
            model = model or self.default_model

            if use_structured_output:
                prompt_data = self.prompt_builder.create_structured_prompt(
                    query, chunks)
                prompt = prompt_data["prompt"]

                # prompt_data["format"] is the raw schema → wrap it properly
                response = self.generate(
                    model=model,
                    prompt=prompt,
                    temperature=0.7,
                    top_p=0.9,
                    response_format={
                        "type": "json_schema",
                        "json_schema": prompt_data["format"],
                    },
                )
            else:
                prompt = self.prompt_builder.create_rag_prompt(query, chunks)
                response = self.generate(
                    model=model,
                    prompt=prompt,
                    temperature=0.7,
                    top_p=0.9,
                    response_format={"type": "json_object"},
                )

            if response and "response" in response:
                raw_response = response["response"]
                logger.debug(f"Raw LLM response: {raw_response[:400]}")
                parsed_response = self.response_parser.parse_structured_response(
                    raw_response)

                # Ensure sources exist
                if not parsed_response.get("sources"):
                    seen, sources = set(), []
                    for chunk in chunks:
                        arxiv_id = chunk.get("arxiv_id")
                        if arxiv_id:
                            clean_id = arxiv_id.split(
                                "v")[0] if "v" in arxiv_id else arxiv_id
                            pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
                            if pdf_url not in seen:
                                sources.append(pdf_url)
                                seen.add(pdf_url)
                    parsed_response["sources"] = sources

                # Add citations if missing
                if not parsed_response.get("citations"):
                    citations = list(
                        set(chunk.get("arxiv_id")
                            for chunk in chunks if chunk.get("arxiv_id"))
                    )
                    parsed_response["citations"] = citations[:5]

                return parsed_response

            raise OllamaException("No structured response generated from LLM")

        except Exception as e:
            logger.error(f"Error generating RAG answer: {e}")
            raise OllamaException(f"Failed to generate RAG answer: {e}")

    def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream RAG answers progressively."""
        try:
            model = model or self.default_model
            prompt = self.prompt_builder.create_rag_prompt(query, chunks)

            for chunk in self.generate_stream(
                model=model,
                prompt=prompt,
                temperature=0.7,
                top_p=0.9,
            ):
                yield chunk

        except Exception as e:
            logger.error(f"Error generating streaming RAG answer: {e}")
            raise OllamaException(
                f"Failed to generate streaming RAG answer: {e}")
