"""Chatty Maps replication pipeline for Zurich.

Implements the methodology from Aiello et al. (2016):
  1. Classify geotagged photos into 6 sound categories via tag matching.
  2. Build buffer polygons around street segments  (Algorithm 1).
  3. Spatial-join photos to segments via PIP        (Algorithm 2).
  4. Compute & z-score-normalise sound profiles     (Algorithm 3).
"""

from typing import List, Dict, Any
from collections import Counter
from geo_proxy.primitives import Point, BoundingBox, Segment, Polygon
from geo_proxy.algorithms import (
    build_segment_buffer,
    point_in_polygon,
    compute_sound_profile,
    zscore_normalise,
    dominant_sound,
    SOUND_CATEGORIES,
)


# ---------------------------------------------------------------------------
# Sound-category dictionaries  (6 categories – Aiello et al., Table 1)
# ---------------------------------------------------------------------------

TRANSPORT_WORDS = {
    'car', 'train', 'bus', 'traffic', 'vehicle', 'highway', 'motor',
    'engine', 'horn', 'siren', 'truck', 'tram', 'motorcycle', 'road',
    'driving', 'taxi', 'bicycle', 'scooter',
}
NATURE_WORDS = {
    'bird', 'water', 'wind', 'leaves', 'river', 'tree', 'rain', 'garden',
    'park', 'forest', 'animal', 'dog', 'cat', 'flower', 'grass', 'lake',
    'sky', 'insect', 'bee', 'creek',
}
HUMAN_WORDS = {
    'talk', 'laugh', 'shout', 'crowd', 'footsteps', 'people', 'voice',
    'children', 'chat', 'applause', 'whisper', 'sing', 'conversation',
    'speech', 'cheer', 'market', 'cafe', 'restaurant', 'bar',
}
MUSIC_WORDS = {
    'music', 'guitar', 'piano', 'drums', 'concert', 'band', 'song',
    'melody', 'jazz', 'rock', 'classical', 'violin', 'flute', 'trumpet',
    'busker', 'festival', 'choir', 'orchestra', 'dj',
}
MECHANICAL_WORDS = {
    'construction', 'drill', 'hammer', 'machine', 'factory', 'generator',
    'compressor', 'saw', 'crane', 'jackhammer', 'demolition', 'industrial',
    'metal', 'welding', 'equipment', 'pump',
}
INDOOR_WORDS = {
    'ac', 'fan', 'refrigerator', 'hum', 'indoor', 'ventilation', 'heating',
    'elevator', 'escalator', 'door', 'office', 'church', 'museum',
    'library', 'station', 'airport', 'hall',
}

CATEGORY_WORD_SETS: Dict[str, set] = {
    'transport':  TRANSPORT_WORDS,
    'nature':     NATURE_WORDS,
    'human':      HUMAN_WORDS,
    'music':      MUSIC_WORDS,
    'mechanical': MECHANICAL_WORDS,
    'indoor':     INDOOR_WORDS,
}


def assign_sound_category(tags: str) -> str:
    """Classify a photo's tags into one of 6 sound categories.

    For each category, count how many dictionary words appear in *tags*.
    The category with the highest count wins.  Ties are broken by the
    ordering in SOUND_CATEGORIES (transport first).  If no words match,
    returns 'unspecified'.
    """
    tag_words = set(tags.lower().split())
    scores = {cat: len(tag_words & words) for cat, words in CATEGORY_WORD_SETS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'unspecified'


# ---------------------------------------------------------------------------
# Spatial-join pipeline
# ---------------------------------------------------------------------------

def spatial_join(
    segments: List[Segment],
    points_with_data: List[Dict[str, Any]],
    buffer_distance: float = 50.0,
) -> List[Dict[str, Any]]:
    """Full Chatty Maps spatial-join pipeline.

    For each street segment:
      1. Build a rectangular buffer polygon (Algorithm 1).
      2. Use the buffer's bbox to quickly filter candidate points.
      3. For each candidate, run point-in-polygon (Algorithm 2) on the
         buffer polygon to decide membership.
      4. Collect category counts of matched points.
      5. Compute the sound profile fractions (Algorithm 3).

    After processing all segments, z-score normalise the profiles and
    assign the dominant (highest z-score) category per segment.

    Returns a list of result dicts, one per segment.
    """

    raw_profiles: List[Dict[str, float]] = []
    segment_meta: List[Dict[str, Any]] = []

    for segment in segments:
        # --- Algorithm 1: build buffer polygon ---
        buffer_poly = build_segment_buffer(segment, buffer_distance)

        # Bbox pre-filter for candidate points (Lectures 3-4)
        candidates = [
            p for p in points_with_data
            if buffer_poly.bbox.contains_point(p['geometry'])
        ]

        # --- Algorithm 2: point-in-polygon test ---
        category_counts: Dict[str, int] = {c: 0 for c in SOUND_CATEGORIES}
        matched = 0
        for p in candidates:
            if point_in_polygon(p['geometry'], buffer_poly):
                category_counts[p['sound_category']] = (
                    category_counts.get(p['sound_category'], 0) + 1
                )
                matched += 1

        # --- Algorithm 3 (step 1): sound profile fractions ---
        profile = compute_sound_profile(category_counts)
        raw_profiles.append(profile)

        # Compute buffer centroid (Lecture 2 – area-weighted)
        centroid = buffer_poly.calculate_centroid()

        segment_meta.append({
            'segment': segment,
            'buffer': buffer_poly,
            'centroid': centroid,
            'category_counts': category_counts,
            'matched_points': matched,
        })

    # --- Algorithm 3 (step 2): z-score normalisation across segments ---
    z_profiles = zscore_normalise(raw_profiles)

    # Assemble final results
    results = []
    for i, meta in enumerate(segment_meta):
        meta['sound_profile'] = raw_profiles[i]
        meta['z_profile'] = z_profiles[i] if z_profiles else {}
        meta['dominant_sound'] = (
            dominant_sound(z_profiles[i])
            if z_profiles and meta['matched_points'] > 0
            else 'none'
        )
        results.append(meta)

    return results
