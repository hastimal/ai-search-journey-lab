"""Core Pydantic models for the AI search journey pipeline."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """Multi-label classification of user search intent."""

    INFORMATIONAL = "informational"
    NAVIGATIONAL = "navigational"
    COMMERCIAL = "commercial"
    TRANSACTIONAL = "transactional"
    LOCAL_DISCOVERY = "local_discovery"


class SearchIntent(BaseModel):
    """Structured intent extracted from the user's natural language request."""

    intent_types: list[IntentType] = Field(default_factory=list)
    category: Optional[str] = None
    reference_location: Optional[str] = None
    group_size: Optional[int] = Field(default=None, gt=0)
    open_after: Optional[str] = None
    open_before: Optional[str] = None
    hard_constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    requested_result_count: int = Field(default=3, gt=0)


class ToolName(str, Enum):
    """Retrieval tool names used in dynamic query fan-out."""

    GOOGLE_PLACES = "google_places"
    GOOGLE_SEARCH = "google_search"


class FanoutQuery(BaseModel):
    """A single dynamic retrieval query task generated during intent fan-out."""

    task_id: Optional[str] = None
    goal: str
    query: str
    tool: ToolName
    reason: Optional[str] = None


class SearchSource(BaseModel):
    """A web source returned by Google Search grounding."""

    title: Optional[str] = None
    url: str


class SearchCitation(BaseModel):
    """A text segment grounding support mapping to web source chunks."""

    start_index: Optional[int] = None
    end_index: Optional[int] = None
    source_indices: list[int] = Field(default_factory=list)
    cited_text: Optional[str] = None


class SearchGroundingResult(BaseModel):
    """Result of executing a google_search task with Gemini + Google Search Grounding."""

    task_id: Optional[str] = None
    planner_query: str
    grounded_text: str
    executed_search_queries: list[str] = Field(default_factory=list)
    sources: list[SearchSource] = Field(default_factory=list)
    citations: list[SearchCitation] = Field(default_factory=list)


class Candidate(BaseModel):
    """Normalized representation of a local candidate place."""

    place_id: str
    name: str
    formatted_address: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    user_rating_count: Optional[int] = Field(default=None, ge=0)
    website_url: Optional[str] = None
    google_maps_url: Optional[str] = None
    opening_hours: list[str] = Field(default_factory=list)
    retrieval_task_ids: list[str] = Field(default_factory=list)


class EvidenceSource(str, Enum):
    """Source provenance for retrieved evidence."""

    GOOGLE_PLACES = "google_places"
    GOOGLE_SEARCH = "google_search"


class Evidence(BaseModel):
    """Evidence item supporting or contradicting a candidate attribute claim."""

    candidate_id: str
    attribute: str
    claim: str
    source: EvidenceSource
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    citation: Optional[str] = None
    planner_query: Optional[str] = None
    fanout_task_id: Optional[str] = None
    fanout_task_ids: list[str] = Field(default_factory=list)
    executed_search_queries: list[str] = Field(default_factory=list)
    source_indices: list[int] = Field(default_factory=list)


class CandidateEvidence(BaseModel):
    """Candidate place linked to its structured Places and unstructured Search evidence."""

    candidate: Candidate
    structured_evidence: list[Evidence] = Field(default_factory=list)
    search_evidence: list[Evidence] = Field(default_factory=list)


class EvidenceAggregationResult(BaseModel):
    """Result of aggregating Places candidates with Search grounding evidence."""

    candidates: list[CandidateEvidence] = Field(default_factory=list)
    unmatched_search_evidence: list[Evidence] = Field(default_factory=list)


class ConstraintStatus(str, Enum):
    """Status of constraint evaluation.

    Note: UNKNOWN is distinct from NOT_SATISFIED and must not automatically
    be treated as false.
    """

    SUPPORTED = "supported"
    UNKNOWN = "unknown"
    NOT_SATISFIED = "not_satisfied"


class ConstraintSupport(BaseModel):
    """A single piece of supporting or contradictory evidence with full provenance."""

    source_type: str
    fanout_task_ids: list[str] = Field(default_factory=list)
    evidence_text: Optional[str] = None
    planner_query: Optional[str] = None
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    citation_indices: list[int] = Field(default_factory=list)


class ConstraintResult(BaseModel):
    """Result of evaluating a specific constraint against a candidate with provenance."""

    constraint: str
    status: ConstraintStatus
    supporting_evidence: list[ConstraintSupport] = Field(default_factory=list)
    explanation: str = ""
    reason: Optional[str] = None

    @property
    def source_type(self) -> Optional[str]:
        """Derived primary or combined source type for backwards compatibility."""
        if not self.supporting_evidence:
            return None
        types = [s.source_type for s in self.supporting_evidence]
        if "google_places" in types and "google_search" in types:
            return "google_places,google_search"
        return types[0]

    @property
    def fanout_task_ids(self) -> list[str]:
        """All unique fanout task IDs across all supporting evidence items."""
        ids: list[str] = []
        for s in self.supporting_evidence:
            for tid in s.fanout_task_ids:
                if tid and tid not in ids:
                    ids.append(tid)
        return ids

    @property
    def fanout_task_id(self) -> Optional[str]:
        """Formatted comma-separated fanout task IDs for backwards compatibility."""
        ids = self.fanout_task_ids
        return ", ".join(ids) if ids else None

    @property
    def evidence_text(self) -> Optional[str]:
        """First available evidence text for backwards compatibility."""
        return self.supporting_evidence[0].evidence_text if self.supporting_evidence else None

    @property
    def source_title(self) -> Optional[str]:
        """First available source title for backwards compatibility."""
        return self.supporting_evidence[0].source_title if self.supporting_evidence else None

    @property
    def source_url(self) -> Optional[str]:
        """First available source URL for backwards compatibility."""
        return self.supporting_evidence[0].source_url if self.supporting_evidence else None

    @property
    def planner_query(self) -> Optional[str]:
        """First available planner query for backwards compatibility."""
        return self.supporting_evidence[0].planner_query if self.supporting_evidence else None


class CandidateConstraintEvaluation(BaseModel):
    """Evaluation of all journey constraints for a single candidate place."""

    candidate: Candidate
    results: list[ConstraintResult] = Field(default_factory=list)


class ConstraintEvaluationResult(BaseModel):
    """Complete candidate-by-constraint evaluation matrix."""

    evaluations: list[CandidateConstraintEvaluation] = Field(default_factory=list)


class RankedCandidate(BaseModel):
    """Candidate place augmented with scoring and constraint match details."""

    candidate: Candidate
    score: float
    constraint_results: list[ConstraintResult] = Field(default_factory=list)
    ranking_reasons: list[str] = Field(default_factory=list)


class GroundedAnswer(BaseModel):
    """Final synthesized answer grounded in retrieved evidence."""

    summary: str
    recommendations: list[RankedCandidate] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class JourneyResult(BaseModel):
    """Complete end-to-end trace payload of the AI search journey."""

    question: str
    intent: SearchIntent
    fanout: list[FanoutQuery] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    ranking: list[RankedCandidate] = Field(default_factory=list)
    answer: Optional[GroundedAnswer] = None
