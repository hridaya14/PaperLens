"""Pydantic models for OpenAI structured outputs."""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResponseMetadata(BaseModel):
    """Metadata describing LLM response quality and completeness."""

    model_config = ConfigDict(extra="forbid")

    confidence: Literal["high", "medium", "low", "unknown"] = Field(
        "unknown", description="Confidence level for the generated answer"
    )
    is_partial: bool = Field(
        False,
        description="True when the answer is incomplete or only partially supported by the context",
    )
    is_unanswerable: bool = Field(
        False,
        description="True when the question cannot be answered from the provided context",
    )
    diagnostics: List[str] = Field(
        default_factory=list,
        description="Notes explaining schema corrections or limitations (for logging/observability)",
    )


class RAGResponse(BaseModel):
    """Structured response model for RAG queries."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    answer: str = Field(
        description="Comprehensive answer based on the provided paper excerpts"
    )
    sources: List[str] = Field(
        default_factory=list,
        description="List of PDF URLs from papers used in the answer",
    )
    citations: List[str] = Field(
        default_factory=list,
        description="Specific arXiv IDs or paper titles referenced in the answer",
    )
    metadata: ResponseMetadata = Field(
        default_factory=ResponseMetadata,
        description="Structured metadata describing quality, completeness, and diagnostics",
    )
    legacy_confidence: Optional[str] = Field(
        default=None,
        alias="confidence",
        exclude=True,
        description="Deprecated top-level confidence field maintained for backward compatibility",
    )

    @model_validator(mode="after")
    def _merge_legacy_confidence(self):
        """Move legacy confidence into metadata for compatibility."""
        if self.legacy_confidence and self.metadata.confidence == "unknown":
            self.metadata.confidence = self.legacy_confidence  # type: ignore[assignment]
        return self
