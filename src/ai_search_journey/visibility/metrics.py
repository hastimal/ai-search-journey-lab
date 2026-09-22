"""Deterministic visibility metrics and trend calculations (V3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from ai_search_journey.visibility.models import (
    VisibilityMetrics,
    VisibilityScanBundle,
)


@dataclass(frozen=True)
class VisibilityTrendPoint:
    """Immutable point in a brand's visibility trajectory over time."""

    scan_id: str
    started_at: datetime
    mentioned: bool
    recommended: bool
    recommendation_position: int | None
    cited: bool
    mention_count: int


def calculate_visibility_metrics(
    bundles: Sequence[VisibilityScanBundle],
    brand_id: str,
) -> VisibilityMetrics:
    """Calculate deterministic visibility metrics for a brand across bundles.

    Only bundles tracking brand_id are included in the denominator.
    Returns full float precision without rounding.
    """
    if not brand_id or not brand_id.strip():
        raise ValueError("brand_id cannot be blank")

    # Filter to tracked bundles containing an observation for brand_id
    tracked_observations = []
    tracked_bundles = []
    for bundle in bundles:
        for obs in bundle.brand_observations:
            if obs.brand_id == brand_id:
                tracked_observations.append(obs)
                tracked_bundles.append(bundle)
                break

    total_scans = len(tracked_observations)

    # Zero-scan state
    if total_scans == 0:
        return VisibilityMetrics(
            brand_id=brand_id,
            total_scans=0,
            mention_rate=0.0,
            recommendation_rate=0.0,
            citation_rate=0.0,
            average_recommendation_position=None,
            share_of_voice=0.0,
            fanout_coverage=0.0,
        )

    # 1. Mention Rate
    mention_count_scans = sum(1 for obs in tracked_observations if obs.mentioned)
    mention_rate = mention_count_scans / total_scans

    # 2. Recommendation Rate
    recommendation_count_scans = sum(1 for obs in tracked_observations if obs.recommended)
    recommendation_rate = recommendation_count_scans / total_scans

    # 3. Citation Rate (owned domain)
    citation_count_scans = sum(1 for obs in tracked_observations if obs.cited)
    citation_rate = citation_count_scans / total_scans

    # 4. Average Recommendation Position
    rec_positions = [
        obs.recommendation_position
        for obs in tracked_observations
        if obs.recommended and obs.recommendation_position is not None
    ]
    avg_rec_pos = (
        sum(rec_positions) / len(rec_positions) if rec_positions else None
    )

    # 5. Share of Voice
    # Selected brand mention count / total mention count across all brands in tracked bundles
    selected_brand_mentions = sum(obs.mention_count for obs in tracked_observations)
    total_market_mentions = sum(
        obs.mention_count
        for b in tracked_bundles
        for obs in b.brand_observations
    )
    if total_market_mentions > 0:
        share_of_voice = selected_brand_mentions / total_market_mentions
    else:
        share_of_voice = 0.0

    # 6. Fan-Out Coverage
    brand_fanouts = [
        fo
        for b in tracked_bundles
        for fo in b.fanout_observations
        if fo.brand_id == brand_id
    ]
    if brand_fanouts:
        found_count = sum(1 for fo in brand_fanouts if fo.brand_found)
        fanout_coverage = found_count / len(brand_fanouts)
    else:
        fanout_coverage = 0.0

    return VisibilityMetrics(
        brand_id=brand_id,
        total_scans=total_scans,
        mention_rate=mention_rate,
        recommendation_rate=recommendation_rate,
        citation_rate=citation_rate,
        average_recommendation_position=avg_rec_pos,
        share_of_voice=share_of_voice,
        fanout_coverage=fanout_coverage,
    )


def calculate_visibility_trend(
    bundles: Sequence[VisibilityScanBundle],
    brand_id: str,
) -> list[VisibilityTrendPoint]:
    """Extract chronological visibility trend points for a brand across bundles.

    Ordered by started_at ascending, with scan_id ascending as tie-breaker.
    """
    if not brand_id or not brand_id.strip():
        raise ValueError("brand_id cannot be blank")

    points: list[VisibilityTrendPoint] = []
    for bundle in bundles:
        for obs in bundle.brand_observations:
            if obs.brand_id == brand_id:
                points.append(
                    VisibilityTrendPoint(
                        scan_id=bundle.scan.scan_id,
                        started_at=bundle.scan.started_at,
                        mentioned=obs.mentioned,
                        recommended=obs.recommended,
                        recommendation_position=obs.recommendation_position,
                        cited=obs.cited,
                        mention_count=obs.mention_count,
                    )
                )
                break

    # Sort started_at ascending, scan_id ascending
    points.sort(key=lambda p: (p.started_at, p.scan_id))
    return points


def calculate_competitor_comparison(
    bundles: Sequence[VisibilityScanBundle],
    brand_ids: Sequence[str],
) -> list[VisibilityMetrics]:
    """Calculate visibility metrics for multiple brands preserving the supplied brand_ids order."""
    results: list[VisibilityMetrics] = []
    for bid in brand_ids:
        if not bid or not bid.strip():
            raise ValueError("brand_id in brand_ids cannot be blank")
        results.append(calculate_visibility_metrics(bundles, bid))
    return results
