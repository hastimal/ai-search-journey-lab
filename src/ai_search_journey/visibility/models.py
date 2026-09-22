"""Pydantic domain models for AI Search Visibility (V3)."""

from datetime import datetime
from enum import Enum
from typing import Self
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_search_journey.models import ToolName


def normalize_domain(raw_domain: str | None) -> str | None:
    """Normalize a domain string per V3 visibility rules:
    - lowercase
    - remove scheme (http://, https://, etc.)
    - remove path, query, and fragment
    - remove leading www.
    - remove trailing dot
    """
    if raw_domain is None:
        return None

    cleaned = raw_domain.strip().lower()
    if not cleaned:
        raise ValueError("Domain cannot be empty or blank")

    # Remove scheme if present
    if "://" in cleaned:
        parsed = urlsplit(cleaned)
        cleaned = parsed.netloc or cleaned.split("://", 1)[1]
    elif cleaned.startswith("//"):
        cleaned = cleaned[2:]

    # Remove path, query, and fragment
    cleaned = cleaned.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]

    # Remove user credentials if present (e.g. user:pass@host)
    if "@" in cleaned:
        cleaned = cleaned.split("@", 1)[1]

    # Remove port if present (e.g. domain:8080)
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[0]

    # Remove leading www.
    while cleaned.startswith("www."):
        cleaned = cleaned[4:]

    # Remove trailing dot
    cleaned = cleaned.rstrip(".")

    if not cleaned:
        raise ValueError("Domain resulted in empty string after normalization")

    return cleaned


def _check_timezone_aware(dt: datetime, field_name: str) -> None:
    """Ensure datetime has timezone information."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


# ======================================================================
# 1. Enums
# ======================================================================


class BrandRole(str, Enum):
    """Role of a brand in a visibility scan or project."""

    TARGET = "target"
    COMPETITOR = "competitor"


class ScanStatus(str, Enum):
    """Execution status of a visibility scan."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ======================================================================
# 2. Domain Models
# ======================================================================


class BrandProfile(BaseModel):
    """Profile definition for a tracked target brand or competitor."""

    brand_id: str
    name: str
    domain: str | None = None
    aliases: list[str] = Field(default_factory=list)
    place_ids: list[str] = Field(default_factory=list)
    domain_aliases: list[str] = Field(default_factory=list)

    @field_validator("brand_id", "name")
    @classmethod
    def _validate_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be blank")
        return v.strip()

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_domain(v)

    @field_validator("aliases")
    @classmethod
    def _validate_aliases(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for alias in v:
            if not alias or not alias.strip():
                raise ValueError("Aliases cannot be blank")
            if alias not in seen:
                seen.add(alias)
                deduped.append(alias)
        return deduped

    @field_validator("place_ids")
    @classmethod
    def _validate_place_ids(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for pid in v:
            if not pid or not pid.strip():
                raise ValueError("Place IDs cannot be blank")
            pid_clean = pid.strip()
            if pid_clean not in seen:
                seen.add(pid_clean)
                deduped.append(pid_clean)
        return deduped

    @field_validator("domain_aliases")
    @classmethod
    def _validate_domain_aliases(cls, v: list[str]) -> list[str]:
        seen_norm: set[str] = set()
        deduped: list[str] = []
        for d in v:
            norm = normalize_domain(d)
            if norm is not None and norm not in seen_norm:
                seen_norm.add(norm)
                deduped.append(norm)
        return deduped


class VisibilityProject(BaseModel):
    """Project tracking a target brand against a set of competitors."""

    project_id: str
    name: str
    target_brand_id: str
    competitor_brand_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    @field_validator("project_id", "name", "target_brand_id")
    @classmethod
    def _validate_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be blank")
        return v.strip()

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, v: datetime) -> datetime:
        _check_timezone_aware(v, "created_at")
        return v

    @field_validator("competitor_brand_ids")
    @classmethod
    def _validate_competitors(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for cid in v:
            if not cid or not cid.strip():
                raise ValueError("Competitor brand ID cannot be blank")
            cid_clean = cid.strip()
            if cid_clean not in seen:
                seen.add(cid_clean)
                deduped.append(cid_clean)
        return deduped

    @model_validator(mode="after")
    def _validate_target_not_in_competitors(self) -> Self:
        if self.target_brand_id in self.competitor_brand_ids:
            raise ValueError(
                f"target_brand_id '{self.target_brand_id}' must not appear in competitor_brand_ids"
            )
        return self


class PromptDefinition(BaseModel):
    """Configured test prompt definition for visibility scanning."""

    prompt_id: str
    prompt_text: str
    category: str
    reference_location: str | None = None
    enabled: bool = True
    created_at: datetime

    @field_validator("prompt_id", "category")
    @classmethod
    def _validate_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be blank")
        return v.strip()

    @field_validator("prompt_text")
    @classmethod
    def _validate_prompt_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("prompt_text cannot be blank")
        return v

    @field_validator("reference_location")
    @classmethod
    def _validate_location(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("reference_location cannot be blank if provided")
        return v.strip() if v is not None else None

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, v: datetime) -> datetime:
        _check_timezone_aware(v, "created_at")
        return v


class VisibilityScan(BaseModel):
    """Metadata and execution record of an individual visibility scan."""

    scan_id: str
    batch_id: str
    project_id: str
    brand_id: str
    brand_name_snapshot: str
    brand_domain_snapshot: str | None = None
    prompt_id: str
    prompt_text_snapshot: str
    model_name: str
    location_snapshot: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    status: ScanStatus = ScanStatus.PENDING
    duration_seconds: float | None = None
    error_code: str | None = None
    error_message: str | None = None

    @field_validator(
        "scan_id",
        "batch_id",
        "project_id",
        "brand_id",
        "brand_name_snapshot",
        "prompt_id",
        "model_name",
    )
    @classmethod
    def _validate_non_blank_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be blank")
        return v.strip()

    @field_validator("prompt_text_snapshot")
    @classmethod
    def _validate_prompt_snapshot(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("prompt_text_snapshot cannot be blank")
        return v

    @field_validator("brand_domain_snapshot")
    @classmethod
    def _validate_brand_domain_snapshot(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_domain(v)

    @field_validator("location_snapshot")
    @classmethod
    def _validate_location_snapshot(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("location_snapshot cannot be blank if provided")
        return v.strip() if v is not None else None

    @field_validator("started_at")
    @classmethod
    def _validate_started_at(cls, v: datetime) -> datetime:
        _check_timezone_aware(v, "started_at")
        return v

    @field_validator("completed_at")
    @classmethod
    def _validate_completed_at(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            _check_timezone_aware(v, "completed_at")
        return v

    @field_validator("duration_seconds")
    @classmethod
    def _validate_duration(cls, v: float | None) -> float | None:
        if v is not None and v < 0.0:
            raise ValueError("duration_seconds cannot be negative")
        return v

    @model_validator(mode="after")
    def _validate_scan_invariants(self) -> Self:
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be earlier than started_at")

        if self.status == ScanStatus.COMPLETED:
            if self.completed_at is None:
                raise ValueError("COMPLETED scan requires completed_at")
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("COMPLETED scan cannot contain error fields")
        elif self.status == ScanStatus.FAILED:
            if self.completed_at is None:
                raise ValueError("FAILED scan requires completed_at")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("FAILED scan requires error_message")
        elif self.status in (ScanStatus.PENDING, ScanStatus.RUNNING):
            if self.completed_at is not None:
                raise ValueError(
                    f"{self.status.value.upper()} scan must not contain completed_at"
                )
            if self.error_code is not None or self.error_message is not None:
                raise ValueError(
                    f"{self.status.value.upper()} scan must not contain error fields"
                )
        return self


class CitationObservation(BaseModel):
    """Observation of a cited URL/domain discovered during search grounding or answer synthesis."""

    scan_id: str
    url: str
    domain: str
    source_type: str
    matched_brand_ids: list[str] = Field(default_factory=list)

    @field_validator("scan_id", "source_type")
    @classmethod
    def _validate_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be blank")
        return v.strip()

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("url cannot be blank")
        return v

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, v: str) -> str:
        norm = normalize_domain(v)
        if norm is None:
            raise ValueError("domain cannot be None or blank in CitationObservation")
        return norm

    @field_validator("matched_brand_ids")
    @classmethod
    def _validate_matched_brand_ids(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for bid in v:
            if not bid or not bid.strip():
                raise ValueError("matched_brand_ids cannot contain blank IDs")
            bid_clean = bid.strip()
            if bid_clean not in seen:
                seen.add(bid_clean)
                deduped.append(bid_clean)
        return deduped


class BrandObservation(BaseModel):
    """Observation record for a brand (target or competitor) within an individual scan."""

    scan_id: str
    brand_id: str
    role: BrandRole
    mentioned: bool = False
    mention_count: int = 0
    first_mention_position: int | None = None
    retrieved: bool = False
    best_retrieval_position: int | None = None
    recommended: bool = False
    recommendation_position: int | None = None
    cited: bool = False
    citation_urls: list[str] = Field(default_factory=list)
    citation_domains: list[str] = Field(default_factory=list)

    @field_validator("scan_id", "brand_id")
    @classmethod
    def _validate_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be blank")
        return v.strip()

    @field_validator("mention_count")
    @classmethod
    def _validate_mention_count(cls, v: int) -> int:
        if v < 0:
            raise ValueError("mention_count must be at least 0")
        return v

    @field_validator("first_mention_position")
    @classmethod
    def _validate_first_mention_pos(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("first_mention_position must be a non-negative integer")
        return v

    @field_validator("best_retrieval_position", "recommendation_position")
    @classmethod
    def _validate_positions(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("Positions must be at least 1 when provided")
        return v

    @field_validator("citation_urls")
    @classmethod
    def _validate_citation_urls(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for url in v:
            if not url or not url.strip():
                raise ValueError("citation_urls cannot contain blank entries")
            if url not in seen:
                seen.add(url)
                deduped.append(url)
        return deduped

    @field_validator("citation_domains")
    @classmethod
    def _validate_citation_domains(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for d in v:
            norm = normalize_domain(d)
            if norm is not None and norm not in seen:
                seen.add(norm)
                deduped.append(norm)
        return deduped

    @model_validator(mode="after")
    def _validate_brand_observation_invariants(self) -> Self:
        if not self.mentioned:
            if self.mention_count != 0 or self.first_mention_position is not None:
                raise ValueError(
                    "mentioned=False requires mention_count=0 and first_mention_position=None"
                )
        else:
            if self.mention_count <= 0 or self.first_mention_position is None:
                raise ValueError(
                    "mentioned=True requires mention_count>0 and first_mention_position"
                )

        if not self.retrieved:
            if self.best_retrieval_position is not None:
                raise ValueError("retrieved=False requires best_retrieval_position=None")
        else:
            if self.best_retrieval_position is None:
                raise ValueError("retrieved=True requires best_retrieval_position")

        if not self.recommended:
            if self.recommendation_position is not None:
                raise ValueError("recommended=False requires recommendation_position=None")
        else:
            if self.recommendation_position is None:
                raise ValueError("recommended=True requires recommendation_position")

        if not self.cited:
            if len(self.citation_urls) > 0 or len(self.citation_domains) > 0:
                raise ValueError("cited=False requires empty citation lists")
        else:
            if len(self.citation_urls) == 0 or len(self.citation_domains) == 0:
                raise ValueError("cited=True requires at least one citation URL and domain")

        return self


class FanoutObservation(BaseModel):
    """Observation of brand retrieval presence across individual fan-out tasks."""

    scan_id: str
    task_id: str
    query_text: str
    tool: str
    brand_id: str
    brand_found: bool = False
    position_in_task: int | None = None

    @field_validator("scan_id", "task_id", "brand_id")
    @classmethod
    def _validate_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be blank")
        return v.strip()

    @field_validator("tool")
    @classmethod
    def _validate_tool(cls, v: ToolName | str) -> str:
        if isinstance(v, ToolName):
            return v.value
        if not isinstance(v, str) or not v.strip():
            raise ValueError("tool cannot be blank")
        normalized = v.strip().lower()
        if normalized == ToolName.GOOGLE_PLACES.value:
            return ToolName.GOOGLE_PLACES.value
        if normalized == ToolName.GOOGLE_SEARCH.value:
            return ToolName.GOOGLE_SEARCH.value
        raise ValueError(
            f"Unsupported tool '{v}'. Must match one of: "
            f"'{ToolName.GOOGLE_PLACES.value}', '{ToolName.GOOGLE_SEARCH.value}'"
        )

    @field_validator("query_text")
    @classmethod
    def _validate_query_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query_text cannot be blank")
        return v

    @field_validator("position_in_task")
    @classmethod
    def _validate_position(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("position_in_task must be at least 1 when provided")
        return v

    @model_validator(mode="after")
    def _validate_fanout_invariants(self) -> Self:
        if not self.brand_found:
            if self.position_in_task is not None:
                raise ValueError("brand_found=False requires position_in_task=None")
        else:
            if self.tool == ToolName.GOOGLE_PLACES.value:
                if self.position_in_task is None or self.position_in_task < 1:
                    raise ValueError(
                        "brand_found=True for Google Places requires position_in_task >= 1"
                    )
            elif self.tool == ToolName.GOOGLE_SEARCH.value:
                if self.position_in_task is not None and self.position_in_task < 1:
                    raise ValueError(
                        "position_in_task for Google Search must be >= 1 when provided"
                    )
        return self


class VisibilityMetrics(BaseModel):
    """Aggregated visibility metrics for a brand across scans."""

    brand_id: str
    total_scans: int
    mention_rate: float
    recommendation_rate: float
    citation_rate: float
    average_recommendation_position: float | None = None
    share_of_voice: float
    fanout_coverage: float

    @field_validator("brand_id")
    @classmethod
    def _validate_brand_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("brand_id cannot be blank")
        return v.strip()

    @field_validator("total_scans")
    @classmethod
    def _validate_total_scans(cls, v: int) -> int:
        if v < 0:
            raise ValueError("total_scans must be at least 0")
        return v

    @field_validator(
        "mention_rate",
        "recommendation_rate",
        "citation_rate",
        "share_of_voice",
        "fanout_coverage",
    )
    @classmethod
    def _validate_rates(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Rates must be between 0.0 and 1.0")
        return v

    @field_validator("average_recommendation_position")
    @classmethod
    def _validate_avg_pos(cls, v: float | None) -> float | None:
        if v is not None and v < 1.0:
            raise ValueError("average_recommendation_position must be at least 1.0")
        return v

    @model_validator(mode="after")
    def _validate_metrics_invariants(self) -> Self:
        if self.total_scans == 0:
            for rate_name in (
                "mention_rate",
                "recommendation_rate",
                "citation_rate",
                "share_of_voice",
                "fanout_coverage",
            ):
                if getattr(self, rate_name) != 0.0:
                    raise ValueError(f"When total_scans=0, {rate_name} must be 0.0")
            if self.average_recommendation_position is not None:
                raise ValueError(
                    "When total_scans=0, average_recommendation_position must be None"
                )
        return self


class VisibilityScanBundle(BaseModel):
    """Complete bundle containing a scan and all associated observations."""

    scan: VisibilityScan
    brand_observations: list[BrandObservation] = Field(default_factory=list)
    fanout_observations: list[FanoutObservation] = Field(default_factory=list)
    citations: list[CitationObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_bundle_invariants(self) -> Self:
        scan_id = self.scan.scan_id

        # Scan ID consistency
        for obs in self.brand_observations:
            if obs.scan_id != scan_id:
                raise ValueError(
                    f"BrandObservation scan_id '{obs.scan_id}' "
                    f"does not match scan.scan_id '{scan_id}'"
                )
        for fo in self.fanout_observations:
            if fo.scan_id != scan_id:
                raise ValueError(
                    f"FanoutObservation scan_id '{fo.scan_id}' "
                    f"does not match scan.scan_id '{scan_id}'"
                )
        for cit in self.citations:
            if cit.scan_id != scan_id:
                raise ValueError(
                    f"CitationObservation scan_id '{cit.scan_id}' "
                    f"does not match scan.scan_id '{scan_id}'"
                )

        # Exactly one TARGET observation
        target_count = sum(
            1 for obs in self.brand_observations if obs.role == BrandRole.TARGET
        )
        if target_count != 1:
            raise ValueError(
                f"Exactly one BrandObservation must have role TARGET, found {target_count}"
            )

        # Unique brand_id in brand_observations
        brand_ids = [obs.brand_id for obs in self.brand_observations]
        if len(brand_ids) != len(set(brand_ids)):
            raise ValueError("A brand ID may appear only once in brand_observations")

        # Unique citations by (scan_id, url, source_type)
        citation_keys: set[tuple[str, str, str]] = set()
        for cit in self.citations:
            key = (cit.scan_id, cit.url.strip(), cit.source_type.strip().lower())
            if key in citation_keys:
                raise ValueError(
                    f"Duplicate citation found for scan_id='{cit.scan_id}', "
                    f"url='{cit.url}', source_type='{cit.source_type}'"
                )
            citation_keys.add(key)

        # Unique fan-out observations by (scan_id, task_id, brand_id)
        fanout_keys: set[tuple[str, str, str]] = set()
        for fo in self.fanout_observations:
            key = (fo.scan_id, fo.task_id, fo.brand_id)
            if key in fanout_keys:
                raise ValueError(
                    f"Duplicate fanout observation found for scan_id='{fo.scan_id}', "
                    f"task_id='{fo.task_id}', brand_id='{fo.brand_id}'"
                )
            fanout_keys.add(key)

        return self
