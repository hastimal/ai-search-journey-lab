"""AI Visibility (V3) domain models, enums, and deterministic observation extractor."""

from ai_search_journey.visibility.extractor import (
    AmbiguousBrandMatchError,
    build_answer_mention_corpus,
    extract_brand_mentions,
    extract_visibility_scan_bundle,
    match_candidate_to_brand,
)
from ai_search_journey.visibility.metrics import (
    VisibilityTrendPoint,
    calculate_competitor_comparison,
    calculate_visibility_metrics,
    calculate_visibility_trend,
)
from ai_search_journey.visibility.models import (
    BrandObservation,
    BrandProfile,
    BrandRole,
    CitationObservation,
    FanoutObservation,
    PromptDefinition,
    ScanStatus,
    VisibilityMetrics,
    VisibilityProject,
    VisibilityScan,
    VisibilityScanBundle,
    normalize_domain,
)
from ai_search_journey.visibility.repository import (
    DuplicateScanError,
    InMemoryVisibilityRepository,
    InvalidRepositoryFilterError,
    VisibilityRepository,
)

__all__ = [
    "AmbiguousBrandMatchError",
    "BrandObservation",
    "BrandProfile",
    "BrandRole",
    "CitationObservation",
    "DuplicateScanError",
    "FanoutObservation",
    "InMemoryVisibilityRepository",
    "InvalidRepositoryFilterError",
    "PromptDefinition",
    "ScanStatus",
    "VisibilityMetrics",
    "VisibilityProject",
    "VisibilityRepository",
    "VisibilityScan",
    "VisibilityScanBundle",
    "VisibilityTrendPoint",
    "build_answer_mention_corpus",
    "calculate_competitor_comparison",
    "calculate_visibility_metrics",
    "calculate_visibility_trend",
    "extract_brand_mentions",
    "extract_visibility_scan_bundle",
    "match_candidate_to_brand",
    "normalize_domain",
]
