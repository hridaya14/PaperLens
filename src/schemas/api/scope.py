"""
API-level schemas for scope profile endpoints.

These are thin wrappers / list-response containers around the core schemas
in src.schemas.scope.profile — the same pattern used by the projects router.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel
from src.schemas.scope.profile import FilterDecisionResponse, ScopeProfileResponse


class ScopeProfileListResponse(BaseModel):
    """Response for GET /scope-profiles."""

    profiles: List[ScopeProfileResponse]
    total: int
    active_profile_id: Optional[UUID] = None


class FilterDecisionListResponse(BaseModel):
    """Paginated response for GET /scope-profiles/{id}/decisions."""

    profile_id: UUID
    decisions: List[FilterDecisionResponse]
    total: int
    # Aggregated stats for quick display without a separate stats call
    acceptance_rate: Optional[float] = None


class DecisionStatsResponse(BaseModel):
    """Response for GET /scope-profiles/{id}/decisions/stats."""

    profile_id: UUID
    total_decisions: int
    ingested: int
    rejected: int
    pending: int
    acceptance_rate: float
    avg_embedding_score: Optional[float]
    avg_composite_score: Optional[float]
    llm_invoked_count: int
    lexical_rejection_count: int


class RecomputeVectorResponse(BaseModel):
    """Response for POST /scope-profiles/{id}/recompute-vector."""

    profile_id: UUID
    vector_dims: int
    seed_papers_used: int
    computed_at: datetime
    message: str


class ActivateProfileResponse(BaseModel):
    """Response for POST /scope-profiles/{id}/activate."""

    profile_id: UUID
    name: str
    version_hash: str
    message: str
