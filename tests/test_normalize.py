"""Unit tests for candidate normalization module."""

from ai_search_journey.models import Candidate
from ai_search_journey.normalize import normalize_candidates


def test_unique_candidates_remain_unchanged() -> None:
    """Candidates with unique Place IDs remain unchanged and in order."""
    c1 = Candidate(place_id="id_1", name="Place 1", rating=4.5)
    c2 = Candidate(place_id="id_2", name="Place 2", rating=4.8)

    result = normalize_candidates([c1, c2])
    assert len(result) == 2
    assert result[0] == c1
    assert result[1] == c2


def test_duplicate_place_ids_collapsed_into_one() -> None:
    """Duplicate Place IDs are collapsed into a single canonical candidate."""
    c1 = Candidate(
        place_id="place_123",
        name="Coffee Spot",
        formatted_address="123 Main St",
        rating=4.5,
    )
    c2 = Candidate(
        place_id="place_123",
        name="Coffee Spot",
        formatted_address="123 Main St",
        rating=4.5,
    )

    result = normalize_candidates([c1, c2])
    assert len(result) == 1
    assert result[0].place_id == "place_123"
    assert result[0].name == "Coffee Spot"
    assert result[0].formatted_address == "123 Main St"


def test_missing_optional_fields_filled_from_subsequent_duplicate() -> None:
    """Missing optional fields in the first duplicate are enriched by subsequent duplicate."""
    c1 = Candidate(
        place_id="place_123",
        name="Local Coffee",
        website_url=None,
        rating=4.2,
        opening_hours=[],
    )
    c2 = Candidate(
        place_id="place_123",
        name="Local Coffee",
        website_url="https://localcoffee.com",
        formatted_address="100 Broadway",
        latitude=29.42,
        longitude=-98.49,
        user_rating_count=150,
        google_maps_url="https://maps.google.com/?cid=123",
        opening_hours=["Monday: 8:00 AM – 10:00 PM"],
    )

    result = normalize_candidates([c1, c2])
    assert len(result) == 1
    canon = result[0]
    assert canon.place_id == "place_123"
    assert canon.name == "Local Coffee"
    assert canon.rating == 4.2  # preserved from first
    assert canon.website_url == "https://localcoffee.com"  # filled from second
    assert canon.formatted_address == "100 Broadway"
    assert canon.latitude == 29.42
    assert canon.longitude == -98.49
    assert canon.user_rating_count == 150
    assert canon.google_maps_url == "https://maps.google.com/?cid=123"
    assert canon.opening_hours == ["Monday: 8:00 AM – 10:00 PM"]


def test_opening_hours_preserved() -> None:
    """Opening hours list is preserved faithfully."""
    hours = ["Monday: 7:00 AM – 9:00 PM", "Tuesday: 7:00 AM – 9:00 PM"]
    c = Candidate(place_id="place_hours", name="Cafe", opening_hours=hours)

    result = normalize_candidates([c])
    assert len(result) == 1
    assert result[0].opening_hours == hours


def test_latitude_longitude_preserved() -> None:
    """Latitude and longitude coordinates are preserved without alteration."""
    c = Candidate(
        place_id="place_geo",
        name="Geo Place",
        latitude=29.4267,
        longitude=-98.4900,
    )

    result = normalize_candidates([c])
    assert len(result) == 1
    assert result[0].latitude == 29.4267
    assert result[0].longitude == -98.4900


def test_google_maps_url_preserved() -> None:
    """Google maps URL is preserved."""
    url = "https://maps.google.com/?cid=999888777"
    c = Candidate(place_id="place_map", name="Map Place", google_maps_url=url)

    result = normalize_candidates([c])
    assert len(result) == 1
    assert result[0].google_maps_url == url


def test_same_name_different_place_ids_not_merged() -> None:
    """Places with identical names but different Place IDs must NOT be merged."""
    c1 = Candidate(
        place_id="chain_loc_1",
        name="Starbucks",
        formatted_address="100 North St",
    )
    c2 = Candidate(
        place_id="chain_loc_2",
        name="Starbucks",
        formatted_address="200 South St",
    )

    result = normalize_candidates([c1, c2])
    assert len(result) == 2
    assert result[0].place_id == "chain_loc_1"
    assert result[0].formatted_address == "100 North St"
    assert result[1].place_id == "chain_loc_2"
    assert result[1].formatted_address == "200 South St"


def test_empty_candidates_input_returns_empty_list() -> None:
    """Empty input returns an empty list."""
    assert normalize_candidates([]) == []
    assert normalize_candidates([[], []]) == []


def test_input_order_remains_stable() -> None:
    """Insertion order of first-seen Place IDs is strictly preserved."""
    c1 = Candidate(place_id="id_b", name="B")
    c2 = Candidate(place_id="id_a", name="A")
    c3 = Candidate(place_id="id_c", name="C")
    c4 = Candidate(place_id="id_b", name="B Duplicate")

    result = normalize_candidates([c1, c2, c3, c4])
    assert [c.place_id for c in result] == ["id_b", "id_a", "id_c"]


def test_accepts_nested_candidate_groups() -> None:
    """Accepts list[list[Candidate]] as returned from multiple retrieval tasks."""
    task1_candidates = [
        Candidate(place_id="id_1", name="Place 1"),
        Candidate(place_id="id_2", name="Place 2"),
    ]
    task2_candidates = [
        Candidate(place_id="id_2", name="Place 2", rating=4.9),
        Candidate(place_id="id_3", name="Place 3"),
    ]

    result = normalize_candidates([task1_candidates, task2_candidates])
    assert len(result) == 3
    assert [c.place_id for c in result] == ["id_1", "id_2", "id_3"]
    assert result[1].rating == 4.9
