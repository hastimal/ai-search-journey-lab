"""Unit tests for Google Maps Static API preview module."""

from urllib.parse import parse_qs, urlparse

import pytest

from ai_search_journey.config import settings
from ai_search_journey.models import Candidate, RankedCandidate
from ai_search_journey.static_map import (
    STATIC_MAP_BASE_URL,
    build_static_map_url,
    generate_static_map,
    redact_api_key_in_url,
)


def _make_candidate(
    place_id: str,
    name: str,
    lat: float | None = None,
    lng: float | None = None,
    rank: int = 1,
    score: float = 50.0,
    google_maps_url: str | None = None,
) -> RankedCandidate:
    return RankedCandidate(
        candidate=Candidate(
            place_id=place_id,
            name=name,
            latitude=lat,
            longitude=lng,
            google_maps_url=google_maps_url,
        ),
        score=score,
        rank=rank,
    )


def test_build_static_map_url_top_3_markers_labels() -> None:
    """Verify only top 3 candidates get markers A, B, C with valid coordinates."""
    candidates = [
        _make_candidate("c1", "Cafe Alpha", 29.4260, -98.4930, rank=1),
        _make_candidate("c2", "Cafe Beta", 29.4270, -98.4920, rank=2),
        _make_candidate("c3", "Cafe Gamma", 29.4280, -98.4910, rank=3),
        _make_candidate("c4", "Cafe Delta", 29.4290, -98.4900, rank=4),
    ]

    result = generate_static_map(candidates, api_key="test_key_123", max_candidates=3)

    assert result.marker_count == 3
    assert len(result.markers) == 3
    assert [m.label for m in result.markers] == ["A", "B", "C"]
    assert [m.candidate_name for m in result.markers] == ["Cafe Alpha", "Cafe Beta", "Cafe Gamma"]
    assert [m.rank for m in result.markers] == [1, 2, 3]

    # Verify query parameters in URL
    parsed = urlparse(result.url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "maps.googleapis.com"
    assert parsed.path == "/maps/api/staticmap"

    params = parse_qs(parsed.query)
    assert params["size"] == ["640x360"]
    assert params["maptype"] == ["roadmap"]
    assert params["key"] == ["test_key_123"]
    assert len(params["markers"]) == 3
    assert params["markers"][0] == "label:A|29.426000,-98.493000"
    assert params["markers"][1] == "label:B|29.427000,-98.492000"
    assert params["markers"][2] == "label:C|29.428000,-98.491000"


def test_build_static_map_url_defaults() -> None:
    """Verify build_static_map_url convenience wrapper returns the full URL string."""
    c = _make_candidate("c1", "Place", 29.4260, -98.4930, rank=1)
    url = build_static_map_url([c], api_key="my_key")
    assert url.startswith(STATIC_MAP_BASE_URL)
    assert "key=my_key" in url
    assert "size=640x360" in url
    assert "maptype=roadmap" in url


def test_redact_api_key_in_url() -> None:
    """Verify API key is redacted in displayed URLs and logs."""
    url = "https://maps.googleapis.com/maps/api/staticmap?size=640x360&markers=label:A|29.4,-98.4&key=AIzaSySecret123"
    redacted = redact_api_key_in_url(url)
    assert "AIzaSySecret123" not in redacted
    assert "key=REDACTED" in redacted
    assert "size=640x360" in redacted

    url_mid = "https://maps.googleapis.com/maps/api/staticmap?key=AIzaSySecret123&size=640x360"
    redacted_mid = redact_api_key_in_url(url_mid)
    assert "AIzaSySecret123" not in redacted_mid
    assert "key=REDACTED&size=640x360" in redacted_mid

    result = generate_static_map(
        [_make_candidate("c1", "Place", 29.4260, -98.4930)],
        api_key="secret_maps_key",
    )
    assert "secret_maps_key" in result.url
    assert "secret_maps_key" not in result.redacted_url
    assert "key=REDACTED" in result.redacted_url


def test_missing_coordinates_skipped_safely() -> None:
    """Candidate with missing lat/lng is skipped while valid candidates are placed."""
    candidates = [
        _make_candidate("c1", "No Coord 1", None, None, rank=1),
        _make_candidate("c2", "Valid Beta", 29.4270, -98.4920, rank=2),
        _make_candidate("c3", "Valid Gamma", 29.4280, -98.4910, rank=3),
    ]

    result = generate_static_map(candidates, api_key="test_key")
    assert result.marker_count == 2
    assert result.markers[0].label == "B"
    assert result.markers[0].candidate_name == "Valid Beta"
    assert result.markers[1].label == "C"
    assert result.markers[1].candidate_name == "Valid Gamma"


def test_zero_valid_coordinates_raises_error() -> None:
    """If no candidate has valid coordinates, raise ValueError."""
    candidates = [
        _make_candidate("c1", "No Coord 1", None, None, rank=1),
        _make_candidate("c2", "No Coord 2", None, None, rank=2),
    ]

    with pytest.raises(ValueError, match="No valid coordinates found"):
        generate_static_map(candidates, api_key="test_key")


def test_missing_api_key_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If GOOGLE_MAPS_API_KEY is not configured, raise ValueError."""
    monkeypatch.setattr(settings, "google_maps_api_key", None)
    c = _make_candidate("c1", "Place", 29.4260, -98.4930)

    with pytest.raises(
        ValueError, match="GOOGLE_MAPS_API_KEY environment variable is not configured"
    ):
        generate_static_map([c])


def test_individual_google_maps_urls_remain_unchanged() -> None:
    """Verify static map generation does not mutate candidate google_maps_url."""
    original_url = "https://maps.google.com/?cid=123456789"
    c = _make_candidate("c1", "Place", 29.4260, -98.4930, google_maps_url=original_url)

    _ = generate_static_map([c], api_key="test_key")
    assert c.candidate.google_maps_url == original_url


def test_custom_dimensions_and_maptype() -> None:
    """Verify configurable width, height, and maptype."""
    c = _make_candidate("c1", "Place", 29.4260, -98.4930)
    result = generate_static_map(
        [c],
        api_key="test_key",
        width=800,
        height=600,
        maptype="satellite",
    )
    assert "size=800x600" in result.url
    assert "maptype=satellite" in result.url
