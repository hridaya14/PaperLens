"""
Repository for scope profiles and paper filter decisions.

Follows the same session/commit/scalar patterns as PaperRepository.
All commits happen inside the repository methods — callers do not
need to manage transaction boundaries except for bulk operations
(e.g. writing many filter decisions in one pipeline run, where the
caller commits once at the end via write_filter_decisions_bulk).
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from src.models.scope_profile import PaperFilterDecision, ScopeProfile
from src.schemas.scope.profile import (
    FilterDecisionCreate,
    ScopeProfileCreate,
    ScopeProfileUpdate,
    compute_scope_version_hash,
)

logger = logging.getLogger(__name__)


class ScopeProfileRepository:
    def __init__(self, session: Session):
        self.session = session

    # -------------------------------------------------------------------------
    # Scope profile — writes
    # -------------------------------------------------------------------------

    def create(self, profile_create: ScopeProfileCreate) -> ScopeProfile:
        """Create a new scope profile.

        Computes the version hash from the profile's content before saving.
        The scope vector is not computed here — call update_scope_vector()
        after the embedding service has produced it.

        :param profile_create: Validated ScopeProfileCreate schema
        :returns: Persisted ScopeProfile ORM instance
        """
        version_hash = compute_scope_version_hash(profile_create)

        db_profile = ScopeProfile(
            name=profile_create.name,
            description=profile_create.description,
            seed_paper_ids=profile_create.seed_paper_ids,
            required_terms=profile_create.required_terms,
            excluded_terms=profile_create.excluded_terms,
            lexical_match_mode=profile_create.lexical_match_mode,
            scoring_weights=profile_create.scoring_weights.model_dump(),
            thresholds=profile_create.thresholds.model_dump(),
            journal_filter=profile_create.journal_filter.model_dump(),
            version_hash=version_hash,
            is_active=profile_create.is_active,
        )

        self.session.add(db_profile)
        self.session.commit()
        self.session.refresh(db_profile)

        logger.info(f"Created scope profile '{db_profile.name}' (id={db_profile.id}, hash={version_hash[:8]}...)")
        return db_profile

    def update(self, profile: ScopeProfile, update_data: ScopeProfileUpdate) -> ScopeProfile:
        """Apply a partial update to a scope profile.

        Recomputes version_hash whenever any content-bearing field changes.
        If the hash changes, clears scope_vector so the pipeline knows to
        recompute it before the next run.

        :param profile: Existing ScopeProfile ORM instance
        :param update_data: Partial update schema (only set fields are applied)
        :returns: Updated ScopeProfile ORM instance
        """
        old_hash = profile.version_hash

        # Apply only the fields that were explicitly set in the request
        update_fields = update_data.model_dump(exclude_unset=True)

        for field, value in update_fields.items():
            # Sub-schemas arrive as dicts or Pydantic models — normalise to dict
            # for JSONB columns
            if hasattr(value, "model_dump"):
                value = value.model_dump()
            setattr(profile, field, value)

        # Recompute version hash — build a temporary ScopeProfileCreate
        # from the updated ORM state to pass into the hash function
        from src.schemas.scope.profile import (
            FilteringThresholds,
            JournalFilterConfig,
            ScopeProfileBase,
            ScoringWeights,
        )

        current_state = ScopeProfileBase(
            name=profile.name,
            description=profile.description,
            seed_paper_ids=profile.seed_paper_ids or [],
            required_terms=profile.required_terms or [],
            excluded_terms=profile.excluded_terms or [],
            lexical_match_mode=profile.lexical_match_mode,
            scoring_weights=ScoringWeights(**(profile.scoring_weights or {})),
            thresholds=FilteringThresholds(**(profile.thresholds or {})),
            journal_filter=JournalFilterConfig(**(profile.journal_filter or {})),
        )
        new_hash = compute_scope_version_hash(current_state)
        profile.version_hash = new_hash

        # If filtering behaviour changed, the old scope vector is invalid
        if new_hash != old_hash:
            profile.scope_vector = None
            profile.scope_vector_computed_at = None
            logger.info(
                f"Scope profile '{profile.name}' content changed "
                f"(hash {old_hash[:8]}... → {new_hash[:8]}...) — scope vector cleared"
            )

        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def set_active(self, profile_id: UUID) -> ScopeProfile:
        """Make one profile active and deactivate all others.

        Performed as two sequential updates in the same transaction so
        there is never a moment with zero active profiles or two active
        profiles simultaneously.

        :param profile_id: UUID of the profile to activate
        :returns: The newly activated ScopeProfile
        :raises ValueError: If no profile with the given ID exists
        """
        profile = self.get_by_id(profile_id)
        if not profile:
            raise ValueError(f"No scope profile found with id={profile_id}")

        # Deactivate all others
        all_profiles = self.get_all()
        for p in all_profiles:
            if p.id != profile_id and p.is_active:
                p.is_active = False
                self.session.add(p)

        # Activate the target
        profile.is_active = True
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)

        logger.info(f"Activated scope profile '{profile.name}' (id={profile_id})")
        return profile

    def update_scope_vector(
        self,
        profile_id: UUID,
        vector: List[float],
    ) -> ScopeProfile:
        """Store a precomputed embedding centroid on the profile.

        Called by the pipeline's scope vector preparation task after
        the embedding service has produced the centroid.

        :param profile_id: UUID of the profile to update
        :param vector: Embedding centroid as a list of floats
        :returns: Updated ScopeProfile ORM instance
        :raises ValueError: If no profile with the given ID exists
        """
        profile = self.get_by_id(profile_id)
        if not profile:
            raise ValueError(f"No scope profile found with id={profile_id}")

        profile.scope_vector = vector
        profile.scope_vector_computed_at = datetime.now(timezone.utc)

        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)

        logger.info(f"Updated scope vector for profile '{profile.name}' (id={profile_id}, dims={len(vector)})")
        return profile

    def delete(self, profile: ScopeProfile) -> None:
        """Hard-delete a scope profile.

        Filter decisions referencing this profile will have their
        scope_profile_id set to NULL (SET NULL FK) — the decisions
        themselves are preserved for audit.

        :param profile: ScopeProfile ORM instance to delete
        :raises ValueError: If attempting to delete the active profile
        """
        if profile.is_active:
            raise ValueError(f"Cannot delete the active scope profile '{profile.name}'. Activate a different profile first.")

        self.session.delete(profile)
        self.session.commit()
        logger.info(f"Deleted scope profile '{profile.name}' (id={profile.id})")

    # -------------------------------------------------------------------------
    # Scope profile — reads
    # -------------------------------------------------------------------------

    def get_by_id(self, profile_id: UUID) -> Optional[ScopeProfile]:
        """Fetch a scope profile by primary key.

        :param profile_id: UUID primary key
        :returns: ScopeProfile ORM instance or None
        """
        stmt = select(ScopeProfile).where(ScopeProfile.id == profile_id)
        return self.session.scalar(stmt)

    def get_active(self) -> Optional[ScopeProfile]:
        """Return the currently active scope profile.

        Returns None if no profile is active — callers should treat this
        as "filtering disabled" and ingest all papers.

        :returns: Active ScopeProfile or None
        """
        stmt = select(ScopeProfile).where(ScopeProfile.is_active == True)
        return self.session.scalar(stmt)

    def get_all(self) -> List[ScopeProfile]:
        """Return all scope profiles ordered by creation date descending.

        :returns: List of ScopeProfile ORM instances
        """
        stmt = select(ScopeProfile).order_by(ScopeProfile.created_at.desc())
        return list(self.session.scalars(stmt))

    def needs_vector_recompute(self, profile: ScopeProfile) -> bool:
        """Check whether the scope vector needs to be recomputed.

        True when:
        - The vector has never been computed (scope_vector is None), or
        - The profile was updated after the vector was last computed

        :param profile: ScopeProfile ORM instance
        :returns: True if recomputation is needed
        """
        if profile.scope_vector is None:
            return True
        if profile.scope_vector_computed_at is None:
            return True
        # Compare timezone-aware datetimes
        updated_at = profile.updated_at
        computed_at = profile.scope_vector_computed_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)
        return updated_at > computed_at

    # -------------------------------------------------------------------------
    # Filter decisions — writes
    # -------------------------------------------------------------------------

    def create_filter_decision(self, decision: FilterDecisionCreate) -> PaperFilterDecision:
        """Persist a single filter decision.

        For bulk writes (e.g. end of a pipeline run) prefer
        write_filter_decisions_bulk() which batches all inserts into
        one commit.

        :param decision: FilterDecisionCreate schema
        :returns: Persisted PaperFilterDecision ORM instance
        """
        db_decision = PaperFilterDecision(**decision.model_dump())
        self.session.add(db_decision)
        self.session.commit()
        self.session.refresh(db_decision)
        return db_decision

    def write_filter_decisions_bulk(self, decisions: List[FilterDecisionCreate]) -> int:
        """Persist multiple filter decisions in a single transaction.

        Skips decisions that would violate the UNIQUE(paper_id, scope_version_hash)
        constraint (i.e. a decision already exists for this paper under this
        scope version). This makes the method safe to call on re-runs.

        :param decisions: List of FilterDecisionCreate schemas
        :returns: Number of decisions actually written
        """
        if not decisions:
            return 0

        written = 0
        for decision in decisions:
            # Check for existing decision under same scope version
            existing = self.get_decision_by_paper_and_version(
                paper_id=decision.paper_id,
                scope_version_hash=decision.scope_version_hash,
            )
            if existing:
                logger.debug(
                    f"Skipping duplicate filter decision for paper "
                    f"{decision.paper_id} under scope version "
                    f"{decision.scope_version_hash[:8]}..."
                )
                continue

            db_decision = PaperFilterDecision(**decision.model_dump())
            self.session.add(db_decision)
            written += 1

        try:
            self.session.commit()
            logger.info(f"Wrote {written}/{len(decisions)} filter decisions to DB")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to commit filter decisions: {e}")
            raise

        return written

    # -------------------------------------------------------------------------
    # Filter decisions — reads
    # -------------------------------------------------------------------------

    def get_decision_by_paper_and_version(
        self,
        paper_id: UUID,
        scope_version_hash: str,
    ) -> Optional[PaperFilterDecision]:
        """Fetch the filter decision for a specific paper + scope version.

        :param paper_id: UUID of the paper
        :param scope_version_hash: Version hash of the scope profile at decision time
        :returns: PaperFilterDecision or None
        """
        stmt = select(PaperFilterDecision).where(
            PaperFilterDecision.paper_id == paper_id,
            PaperFilterDecision.scope_version_hash == scope_version_hash,
        )
        return self.session.scalar(stmt)

    def get_decisions_by_paper(self, paper_id: UUID) -> List[PaperFilterDecision]:
        """All filter decisions ever made for a paper, newest first.

        Useful for showing a paper's full decision history as the scope
        evolved over time.

        :param paper_id: UUID of the paper
        :returns: List of PaperFilterDecision ORM instances
        """
        stmt = (
            select(PaperFilterDecision)
            .where(PaperFilterDecision.paper_id == paper_id)
            .order_by(PaperFilterDecision.decided_at.desc())
        )
        return list(self.session.scalars(stmt))

    def get_decisions_by_profile(
        self,
        profile_id: UUID,
        decision: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[PaperFilterDecision], int]:
        """Paginated filter decisions for a scope profile.

        :param profile_id: UUID of the scope profile
        :param decision: Optional filter: 'ingested', 'rejected', or 'pending'
        :param limit: Page size
        :param offset: Page offset
        :returns: Tuple of (decisions list, total count)
        """
        stmt = select(PaperFilterDecision).where(PaperFilterDecision.scope_profile_id == profile_id)
        if decision:
            stmt = stmt.where(PaperFilterDecision.decision == decision)

        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        stmt = stmt.order_by(PaperFilterDecision.decided_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt)), total

    def get_decision_stats(self, profile_id: UUID) -> Dict:
        """Aggregate statistics for a profile's filter decisions.

        Useful for the reporting task and for the frontend audit view
        to show acceptance/rejection rates and average scores.

        :param profile_id: UUID of the scope profile
        :returns: Dictionary of aggregated statistics
        """
        base_stmt = select(PaperFilterDecision).where(PaperFilterDecision.scope_profile_id == profile_id)
        total = self.session.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        if total == 0:
            return {
                "total_decisions": 0,
                "ingested": 0,
                "rejected": 0,
                "pending": 0,
                "acceptance_rate": 0.0,
                "avg_embedding_score": None,
                "avg_composite_score": None,
                "llm_invoked_count": 0,
                "lexical_rejection_count": 0,
            }

        def count_where(extra_where) -> int:
            s = select(func.count()).select_from(base_stmt.where(extra_where).subquery())
            return self.session.scalar(s) or 0

        ingested = count_where(PaperFilterDecision.decision == "ingested")
        rejected = count_where(PaperFilterDecision.decision == "rejected")
        pending = count_where(PaperFilterDecision.decision == "pending")
        llm_invoked = count_where(PaperFilterDecision.llm_relevant != None)
        lexical_rejected = count_where(PaperFilterDecision.lexical_passed == False)

        avg_stmt = select(
            func.avg(PaperFilterDecision.embedding_score),
            func.avg(PaperFilterDecision.composite_score),
        ).where(PaperFilterDecision.scope_profile_id == profile_id)

        avg_embedding, avg_composite = self.session.execute(avg_stmt).one()

        return {
            "total_decisions": total,
            "ingested": ingested,
            "rejected": rejected,
            "pending": pending,
            "acceptance_rate": round(ingested / total * 100, 1) if total > 0 else 0.0,
            "avg_embedding_score": round(float(avg_embedding), 4) if avg_embedding else None,
            "avg_composite_score": round(float(avg_composite), 4) if avg_composite else None,
            "llm_invoked_count": llm_invoked,
            "lexical_rejection_count": lexical_rejected,
        }
