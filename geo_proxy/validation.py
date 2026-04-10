"""Validation module for the Chatty Maps Zurich replication.

Implements Spearman rank correlation (from scratch, no external dependencies)
to compare predicted dominant sound categories against official noise
measurement data, following the validation approach in Aiello et al. (2016).
"""

import csv
import math
import logging
from typing import List, Dict, Any, Tuple
from geo_proxy.primitives import Point, Segment
from geo_proxy.algorithms import point_to_segment_distance, SOUND_CATEGORIES
from geo_proxy.pipeline import assign_sound_category, spatial_join


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def parse_csv_points(file_path: str) -> List[Dict[str, Any]]:
    """Parse a CSV of geotagged sound observations into point dicts."""
    points: List[Dict[str, Any]] = []
    try:
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                lat = float(row.get('latitude', row.get('lat', 0)))
                lon = float(row.get('longitude', row.get('lon', 0)))
                tags = row.get('tags', row.get('description', ''))
                points.append({
                    'geometry': Point(lon, lat),
                    'sound_category': assign_sound_category(tags),
                })
    except Exception as e:
        logging.error(f"Failed parsing CSV: {e}")
    return points


def parse_csv_segments(file_path: str) -> List[Segment]:
    """Parse a CSV of street segments."""
    segments: List[Segment] = []
    try:
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                s_lat = float(row['start_lat'])
                s_lon = float(row['start_lon'])
                e_lat = float(row['end_lat'])
                e_lon = float(row['end_lon'])
                segments.append(Segment(Point(s_lon, s_lat), Point(e_lon, e_lat)))
    except Exception as e:
        logging.error(f"Failed parsing segments CSV: {e}")
    return segments


def parse_csv_noise(file_path: str) -> List[Dict[str, Any]]:
    """Parse a CSV of official noise measurement points (dB levels)."""
    data: List[Dict[str, Any]] = []
    try:
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                lat = float(row.get('latitude', row.get('lat', 0)))
                lon = float(row.get('longitude', row.get('lon', 0)))
                db = float(row.get('db_level', row.get('noise_db', 0)))
                data.append({
                    'geometry': Point(lon, lat),
                    'db_level': db,
                })
    except Exception as e:
        logging.error(f"Failed parsing noise CSV: {e}")
    return data


# ---------------------------------------------------------------------------
# Spearman rank correlation (implemented from scratch – zero dependencies)
# ---------------------------------------------------------------------------

def _rank(values: List[float]) -> List[float]:
    """Assign ranks to a list of values, handling ties with average rank."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        # Find all tied values
        while j < n and indexed[j][1] == indexed[i][1]:
            j += 1
        # Average rank for the tie group (1-based)
        avg_rank = (i + j + 1) / 2.0  # average of (i+1) .. j
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def spearman_rank_correlation(x: List[float], y: List[float]) -> float:
    """Compute Spearman's rank correlation coefficient.

    ρ = 1 - (6 * Σ d_i²) / (n * (n² - 1))

    where d_i = rank(x_i) - rank(y_i).

    This is the standard formula when there are no ties.  When ties exist
    we use the Pearson correlation on ranked values for correctness.

    Returns a value in [-1, 1].
    """
    n = len(x)
    if n < 2:
        return 0.0

    rx = _rank(x)
    ry = _rank(y)

    # Pearson on ranks (handles ties correctly)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((rx[i] - mean_rx) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i] - mean_ry) ** 2 for i in range(n)))

    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


# ---------------------------------------------------------------------------
# Validation pipeline
# ---------------------------------------------------------------------------

def run_validation(
    pipeline_results: List[Dict[str, Any]],
    noise_data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate pipeline output against official noise measurements.

    For each street segment:
      - Find the closest noise measurement point.
      - Record its dB level and the segment's transport sound z-score.

    Then compute Spearman rank correlation between transport z-scores and
    dB levels.  A positive correlation supports the hypothesis that
    social-media-derived sound maps capture real urban noise patterns.
    """
    transport_scores: List[float] = []
    db_levels: List[float] = []

    for result in pipeline_results:
        seg = result['segment']
        z_profile = result.get('z_profile', {})

        # Find closest noise measurement to this segment
        min_dist = float('inf')
        closest_db = None
        for nd in noise_data:
            d = point_to_segment_distance(nd['geometry'], seg)
            if d < min_dist:
                min_dist = d
                closest_db = nd['db_level']

        if closest_db is not None and min_dist < 200:  # within 200 m
            transport_scores.append(z_profile.get('transport', 0.0))
            db_levels.append(closest_db)

    rho = spearman_rank_correlation(transport_scores, db_levels)

    return {
        'spearman_rho': rho,
        'n_matched_segments': len(transport_scores),
        'interpretation': (
            'Positive correlation supports the Chatty Maps hypothesis.'
            if rho > 0 else
            'Weak or negative correlation – further investigation needed.'
        ),
    }


# ---------------------------------------------------------------------------
# Quick demo with Zurich coordinates
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Demo segment in central Zurich (Bahnhofstrasse area)
    p1 = Point(8.5393, 47.3769)
    p2 = Point(8.5401, 47.3773)
    segment = Segment(p1, p2)

    print("Demo: Zurich pipeline validation")
    print(f"Segment length: {segment.length():.1f} m")

    # Synthetic demo point
    points_data = [
        {'geometry': Point(8.5397, 47.3771), 'sound_category': 'transport'}
    ]

    results = spatial_join([segment], points_data, buffer_distance=50.0)
    print(f"Pipeline result: {len(results)} segments analysed.")
    for r in results:
        print(f"  Dominant sound: {r['dominant_sound']}  "
              f"(matched points: {r['matched_points']})")
