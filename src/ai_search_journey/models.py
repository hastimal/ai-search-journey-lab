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


class ConstraintResult(BaseModel):
    """Result of evaluating a specific constraint against a candidate."""

    constraint: str
    status: ConstraintStatus
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)


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
