"""Google Maps Static API preview module for AI Search Journey."""

from typing import Optional
from urllib.parse import urlencode

from ai_search_journey.config import settings
from ai_search_journey.models import MapMarker, RankedCandidate, StaticMapResult

STATIC_MAP_BASE_URL = "https://maps.googleapis.com/maps/api/staticmap"

MARKER_LABELS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]


def redact_api_key_in_url(url: str, placeholder: str = "REDACTED") -> str:
    """Safely redact the API key parameter from a URL for display and logging."""
    if "key=" not in url:
        return url
    prefix, _, suffix = url.partition("key=")
    # Find next query param delimiter if present
    if "&" in suffix:
        _, delim, rest = suffix.partition("&")
        return f"{prefix}key={placeholder}&{rest}"
    return f"{prefix}key={placeholder}"


def build_static_map_url(
    ranked_candidates: list[RankedCandidate],
    *,
    api_key: Optional[str] = None,
    max_candidates: int = 3,
    width: int = 640,
    height: int = 360,
    maptype: str = "roadmap",
) -> str:
    """Build a Google Maps Static API URL for the top ranked candidates.

    Args:
        ranked_candidates: List of ranked candidates.
        api_key: Optional Google Maps API Key override.
        max_candidates: Maximum candidate markers to place (default: 3).
        width: Image width in pixels (default: 640).
        height: Image height in pixels (default: 360).
        maptype: Map type (default: 'roadmap').

    Returns:
        Fully-formed Static Maps URL including API key.

    Raises:
        ValueError: If GOOGLE_MAPS_API_KEY is not configured or no valid coordinates exist.
    """
    result = generate_static_map(
        ranked_candidates,
        api_key=api_key,
        max_candidates=max_candidates,
        width=width,
        height=height,
        maptype=maptype,
    )
    return result.url


def generate_static_map(
    ranked_candidates: list[RankedCandidate],
    *,
    api_key: Optional[str] = None,
    max_candidates: int = 3,
    width: int = 640,
    height: int = 360,
    maptype: str = "roadmap",
) -> StaticMapResult:
    """Generate structured StaticMapResult with URL and marker metadata for Top candidates.

    Args:
        ranked_candidates: List of ranked candidates.
        api_key: Optional Google Maps API Key override.
        max_candidates: Maximum candidate markers to place (default: 3).
        width: Image width in pixels (default: 640).
        height: Image height in pixels (default: 360).
        maptype: Map type (default: 'roadmap').

    Returns:
        StaticMapResult containing real URL, redacted display URL, and marker list.

    Raises:
        ValueError: If GOOGLE_MAPS_API_KEY is not configured or no valid coordinates exist.
    """
    effective_api_key = api_key or settings.google_maps_api_key
    if not effective_api_key or effective_api_key == "your_google_maps_api_key_here":
        raise ValueError("GOOGLE_MAPS_API_KEY environment variable is not configured.")

    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid dimensions {width}x{height}. Width and height must be positive.")

    # Slice at most max_candidates
    candidates_to_map = ranked_candidates[:max_candidates]

    markers_meta: list[MapMarker] = []
    marker_params: list[str] = []

    for idx, ranked_cand in enumerate(candidates_to_map):
        cand = ranked_cand.candidate
        if cand.latitude is None or cand.longitude is None:
            continue

        label = MARKER_LABELS[idx] if idx < len(MARKER_LABELS) else str(idx + 1)
        markers_meta.append(
            MapMarker(
                label=label,
                rank=ranked_cand.rank,
                candidate_name=cand.name,
                latitude=cand.latitude,
                longitude=cand.longitude,
            )
        )
        # Construct marker string: label:A|lat,lng
        marker_params.append(f"label:{label}|{cand.latitude:.6f},{cand.longitude:.6f}")

    if not markers_meta:
        raise ValueError(
            f"No valid coordinates found among the top {len(candidates_to_map)} candidates "
            "to generate a static map."
        )

    # Base query parameters (size, maptype)
    query_params: list[tuple[str, str]] = [
        ("size", f"{width}x{height}"),
        ("maptype", maptype),
    ]

    # Add each marker as a separate 'markers' parameter
    for m in marker_params:
        query_params.append(("markers", m))

    # Real URL with actual key
    real_query = list(query_params)
    real_query.append(("key", effective_api_key))
    real_url = f"{STATIC_MAP_BASE_URL}?{urlencode(real_query)}"

    # Redacted URL for logs / demo presentation
    redacted_query = list(query_params)
    redacted_query.append(("key", "REDACTED"))
    redacted_url = f"{STATIC_MAP_BASE_URL}?{urlencode(redacted_query)}"

    return StaticMapResult(
        url=real_url,
        redacted_url=redacted_url,
        marker_count=len(markers_meta),
        markers=markers_meta,
    )
