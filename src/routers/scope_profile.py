"""
Scope profiles router.

Endpoints:
  POST   /scope-profiles                          create profile
  GET    /scope-profiles                          list all profiles
  GET    /scope-profiles/{id}                     get profile detail
  PATCH  /scope-profiles/{id}                     partial update
  DELETE /scope-profiles/{id}                     delete profile
  POST   /scope-profiles/{id}/activate            make this profile active
  POST   /scope-profiles/{id}/recompute-vector    recompute embedding centroid
  GET    /scope-profiles/{id}/decisions           paginated filter decisions
  GET    /scope-profiles/{id}/decisions/stats     aggregated decision statistics
"""

import logging
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from src.dependencies import EmbeddingsDep, SessionDep
from src.repositories.paper import PaperRepository
from src.repositories.scope_profile import ScopeProfileRepository
from src.schemas.api.scope import (
    ActivateProfileResponse,
    DecisionStatsResponse,
    FilterDecisionListResponse,
    RecomputeVectorResponse,
    ScopeProfileListResponse,
)
from src.schemas.scope.profile import (
    ScopeProfileCreate,
    ScopeProfileResponse,
    ScopeProfileUpdate,
)
from src.services.filtering.embedding import compute_scope_vector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scope-profiles", tags=["scope-profiles"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_profile_or_404(repo: ScopeProfileRepository, profile_id: str):
    """Parse UUID and fetch profile, raising 404 if not found.

    Follows the same pattern as _get_project_or_404 in projects.py.
    """
    try:
        pid = uuid_lib.UUID(profile_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{profile_id}' is not a valid UUID.",
        )
    profile = repo.get_by_id(pid)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope profile '{profile_id}' not found.",
        )
    return profile, pid


def _profile_to_response(profile) -> ScopeProfileResponse:
    """Convert ORM instance to response schema."""
    from src.schemas.scope.profile import (
        FilteringThresholds,
        JournalFilterConfig,
        ScoringWeights,
    )

    return ScopeProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        seed_paper_ids=profile.seed_paper_ids or [],
        required_terms=profile.required_terms or [],
        excluded_terms=profile.excluded_terms or [],
        lexical_match_mode=profile.lexical_match_mode or "any",
        scoring_weights=ScoringWeights(**(profile.scoring_weights or {})),
        thresholds=FilteringThresholds(**(profile.thresholds or {})),
        journal_filter=JournalFilterConfig(**(profile.journal_filter or {})),
        is_active=profile.is_active,
        version_hash=profile.version_hash,
        has_scope_vector=profile.has_scope_vector,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ScopeProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new scope profile",
    description=(
        "Creates a new research scope profile. The scope vector is not computed "
        "immediately — call POST /scope-profiles/{id}/recompute-vector after "
        "creation, or it will be computed automatically at the next pipeline run."
    ),
)
def create_scope_profile(
    body: ScopeProfileCreate,
    db: SessionDep,
) -> ScopeProfileResponse:
    repo = ScopeProfileRepository(db)
    profile = repo.create(body)
    logger.info(f"Created scope profile '{profile.name}' (id={profile.id})")
    return _profile_to_response(profile)


@router.get(
    "",
    response_model=ScopeProfileListResponse,
    summary="List all scope profiles",
)
def list_scope_profiles(db: SessionDep) -> ScopeProfileListResponse:
    repo = ScopeProfileRepository(db)
    profiles = repo.get_all()
    active = repo.get_active()
    return ScopeProfileListResponse(
        profiles=[_profile_to_response(p) for p in profiles],
        total=len(profiles),
        active_profile_id=active.id if active else None,
    )


@router.get(
    "/{profile_id}",
    response_model=ScopeProfileResponse,
    summary="Get a scope profile by ID",
)
def get_scope_profile(
    profile_id: str,
    db: SessionDep,
) -> ScopeProfileResponse:
    repo = ScopeProfileRepository(db)
    profile, _ = _get_profile_or_404(repo, profile_id)
    return _profile_to_response(profile)


@router.patch(
    "/{profile_id}",
    response_model=ScopeProfileResponse,
    summary="Partially update a scope profile",
    description=(
        "Updates only the fields present in the request body. "
        "If any content-bearing field changes (description, seed_paper_ids, "
        "required_terms, excluded_terms, weights, or thresholds), the version "
        "hash is recomputed and the scope vector is cleared — it will be "
        "recomputed at the next pipeline run or on manual trigger."
    ),
)
def update_scope_profile(
    profile_id: str,
    body: ScopeProfileUpdate,
    db: SessionDep,
) -> ScopeProfileResponse:
    repo = ScopeProfileRepository(db)
    profile, _ = _get_profile_or_404(repo, profile_id)

    old_hash = profile.version_hash
    profile = repo.update(profile, body)

    if profile.version_hash != old_hash:
        logger.info(
            f"Scope profile '{profile.name}' updated — version hash changed, scope vector cleared (will recompute on next run)"
        )
    return _profile_to_response(profile)


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scope profile",
    description=(
        "Deletes the profile. Cannot delete the active profile — "
        "activate a different profile first. Filter decisions referencing "
        "this profile are preserved with scope_profile_id set to NULL."
    ),
)
def delete_scope_profile(
    profile_id: str,
    db: SessionDep,
) -> None:
    repo = ScopeProfileRepository(db)
    profile, _ = _get_profile_or_404(repo, profile_id)

    try:
        repo.delete(profile)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    logger.info(f"Deleted scope profile '{profile.name}' (id={profile_id})")


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


@router.post(
    "/{profile_id}/activate",
    response_model=ActivateProfileResponse,
    summary="Make this profile the active one",
    description=(
        "Deactivates all other profiles and activates this one. The pipeline will use this profile from the next scheduled run."
    ),
)
def activate_scope_profile(
    profile_id: str,
    db: SessionDep,
) -> ActivateProfileResponse:
    repo = ScopeProfileRepository(db)
    _, pid = _get_profile_or_404(repo, profile_id)

    try:
        profile = repo.set_active(pid)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return ActivateProfileResponse(
        profile_id=profile.id,
        name=profile.name,
        version_hash=profile.version_hash,
        message=f"Profile '{profile.name}' is now active. It will be used from the next pipeline run.",
    )


# ---------------------------------------------------------------------------
# Scope vector recomputation
# ---------------------------------------------------------------------------


@router.post(
    "/{profile_id}/recompute-vector",
    response_model=RecomputeVectorResponse,
    summary="Recompute the embedding centroid for this profile",
    description=(
        "Embeds the profile description and any seed paper abstracts, "
        "averages them into a centroid vector, and stores it on the profile. "
        "Call this after creating a profile or after the vector is cleared by an update. "
        "The pipeline also runs this automatically if the vector is stale."
    ),
)
async def recompute_scope_vector(
    profile_id: str,
    db: SessionDep,
    embeddings_service: EmbeddingsDep,
) -> RecomputeVectorResponse:
    repo = ScopeProfileRepository(db)
    profile, pid = _get_profile_or_404(repo, profile_id)

    # Fetch seed paper abstracts from DB
    seed_abstracts = []
    seed_paper_ids = profile.seed_paper_ids or []
    if seed_paper_ids:
        paper_repo = PaperRepository(db)
        for arxiv_id in seed_paper_ids:
            paper = paper_repo.get_by_arxiv_id(arxiv_id)
            if paper and paper.abstract:
                seed_abstracts.append(paper.abstract)
            else:
                logger.warning(
                    f"Seed paper '{arxiv_id}' not found in DB or has no abstract — skipping from scope vector computation"
                )

    try:
        vector = await compute_scope_vector(
            profile=profile,
            embeddings_client=embeddings_service,
            seed_paper_abstracts=seed_abstracts if seed_abstracts else None,
        )
    except Exception as e:
        logger.error(f"Scope vector computation failed for profile '{profile.name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute scope vector: {str(e)}",
        )

    repo.update_scope_vector(pid, vector)

    return RecomputeVectorResponse(
        profile_id=pid,
        vector_dims=len(vector),
        seed_papers_used=len(seed_abstracts),
        computed_at=datetime.now(timezone.utc),
        message=(
            f"Scope vector computed from 1 description + {len(seed_abstracts)} seed paper abstract(s). Dims: {len(vector)}."
        ),
    )


# ---------------------------------------------------------------------------
# Filter decisions — audit log
# ---------------------------------------------------------------------------


@router.get(
    "/{profile_id}/decisions",
    response_model=FilterDecisionListResponse,
    summary="Paginated filter decisions for a scope profile",
    description=(
        "Returns every ingest/reject decision made under this profile. "
        "Use the 'decision' query param to filter by outcome. "
        "Useful for auditing filter quality and tuning thresholds."
    ),
)
def list_filter_decisions(
    profile_id: str,
    db: SessionDep,
    decision: Optional[str] = Query(
        default=None,
        description="Filter by outcome: 'ingested', 'rejected', or 'pending'",
        pattern="^(ingested|rejected|pending)$",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> FilterDecisionListResponse:
    repo = ScopeProfileRepository(db)
    profile, pid = _get_profile_or_404(repo, profile_id)

    decisions, total = repo.get_decisions_by_profile(
        profile_id=pid,
        decision=decision,
        limit=limit,
        offset=offset,
    )

    from src.schemas.scope.profile import FilterDecisionResponse

    acceptance_rate = None
    if not decision:
        # Only compute acceptance rate when showing all decisions
        stats = repo.get_decision_stats(pid)
        acceptance_rate = stats.get("acceptance_rate")

    return FilterDecisionListResponse(
        profile_id=pid,
        decisions=[FilterDecisionResponse.model_validate(d) for d in decisions],
        total=total,
        acceptance_rate=acceptance_rate,
    )


@router.get(
    "/{profile_id}/decisions/stats",
    response_model=DecisionStatsResponse,
    summary="Aggregated filter decision statistics",
    description=(
        "Returns acceptance/rejection rates, average scores, and LLM invocation "
        "counts for this profile. Useful for threshold tuning."
    ),
)
def get_decision_stats(
    profile_id: str,
    db: SessionDep,
) -> DecisionStatsResponse:
    repo = ScopeProfileRepository(db)
    _, pid = _get_profile_or_404(repo, profile_id)

    stats = repo.get_decision_stats(pid)
    return DecisionStatsResponse(profile_id=pid, **stats)
