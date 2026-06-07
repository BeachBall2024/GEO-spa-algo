"""Chatty Maps replication pipeline for Zurich.

Implements the methodology from Aiello et al. (2016):
  1. Classify geotagged photos into 6 sound categories via tag matching.
  2. Build buffer polygons around street segments  (Algorithm 1).
  3. Spatial-join photos to segments via PIP        (Algorithm 2).
  4. Compute & z-score-normalise sound profiles     (Algorithm 3).
"""

import re
import math
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
    'auto', 'autos', 'verkehr', 'strasse', 'zug', 'bahn', 'gleis',
    'flugzeug', 'flughafen',
}
NATURE_WORDS = {
    'bird', 'water', 'wind', 'leaves', 'river', 'tree', 'rain', 'garden',
    'park', 'forest', 'animal', 'dog', 'cat', 'flower', 'grass', 'lake',
    'sky', 'insect', 'bee', 'creek',
    'wasser', 'fluss', 'see', 'regen', 'wald', 'baum', 'hund', 'katze',
}
HUMAN_WORDS = {
    'talk', 'laugh', 'shout', 'crowd', 'footsteps', 'people', 'voice',
    'children', 'chat', 'applause', 'whisper', 'sing', 'conversation',
    'speech', 'cheer', 'market', 'cafe', 'restaurant', 'bar',
    'menschen', 'markt', 'kinder', 'spielplatz',
}
MUSIC_WORDS = {
    'music', 'guitar', 'piano', 'drums', 'concert', 'band', 'song',
    'melody', 'jazz', 'rock', 'classical', 'violin', 'flute', 'trumpet',
    'busker', 'festival', 'choir', 'orchestra', 'dj',
    'musik', 'konzert', 'lied',
}
MECHANICAL_WORDS = {
    'construction', 'drill', 'hammer', 'machine', 'factory', 'generator',
    'compressor', 'saw', 'crane', 'jackhammer', 'demolition', 'industrial',
    'metal', 'welding', 'equipment', 'pump',
    'baustelle', 'bau', 'maschine', 'maschinen', 'industrie', 'sirene',
    'hupe',
}
INDOOR_WORDS = {
    'ac', 'fan', 'refrigerator', 'hum', 'indoor', 'ventilation', 'heating',
    'elevator', 'escalator', 'door', 'office', 'church', 'museum',
    'library', 'station', 'airport', 'hall',
    'haus', 'wohnung', 'zimmer', 'office', 'kirche', 'glocke',
}

CATEGORY_WORD_SETS: Dict[str, set] = {
    'transport':  TRANSPORT_WORDS,
    'nature':     NATURE_WORDS,
    'human':      HUMAN_WORDS,
    'music':      MUSIC_WORDS,
    'mechanical': MECHANICAL_WORDS,
    'indoor':     INDOOR_WORDS,
}


TAG_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize_tags(tags: str) -> set:
    """Return normalized tag tokens from Flickr's messy tag strings.

    The full Flickr export mixes spaces, commas, hashtags and values such as
    ``uploaded:by=instagram``. A regex tokenizer is more reliable than a plain
    ``split()`` and keeps the pipeline independent from pandas/geopandas.
    """
    if tags is None:
        return set()
    return set(TAG_TOKEN_RE.findall(str(tags).lower()))


def assign_sound_category(tags: str) -> str:
    """Classify a photo's tags into one of 6 sound categories.

    For each category, count how many dictionary words appear in *tags*.
    The category with the highest count wins.  Ties are broken by the
    ordering in SOUND_CATEGORIES (transport first).  If no words match,
    returns 'unspecified'.
    """
    tag_words = tokenize_tags(tags)
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

    # A tiny uniform grid avoids the expensive pattern of checking every
    # Flickr point against every segment buffer. The ray-casting test is still
    # exact; the grid only narrows down candidate points by bbox.
    cell_size = 0.005  # degrees, roughly 380 m east-west in Zurich
    point_grid: Dict[tuple, List[Dict[str, Any]]] = {}
    for point_data in points_with_data:
        point = point_data['geometry']
        key = (
            math.floor(point.x / cell_size),
            math.floor(point.y / cell_size),
        )
        point_grid.setdefault(key, []).append(point_data)

    def candidates_for_bbox(bbox: BoundingBox) -> List[Dict[str, Any]]:
        min_x = math.floor(bbox.min_x / cell_size)
        max_x = math.floor(bbox.max_x / cell_size)
        min_y = math.floor(bbox.min_y / cell_size)
        max_y = math.floor(bbox.max_y / cell_size)
        candidates: List[Dict[str, Any]] = []
        for ix in range(min_x, max_x + 1):
            for iy in range(min_y, max_y + 1):
                candidates.extend(point_grid.get((ix, iy), []))
        return candidates

    for segment in segments:
        # --- Algorithm 1: build buffer polygon ---
        buffer_poly = build_segment_buffer(segment, buffer_distance)

        # Bbox pre-filter for candidate points (Lectures 3-4)
        candidates = [
            p for p in candidates_for_bbox(buffer_poly.bbox)
            if buffer_poly.bbox.contains_point(p['geometry'])
        ]

        # --- Algorithm 2: point-in-polygon test ---
        category_counts: Dict[str, int] = {c: 0 for c in SOUND_CATEGORIES}
        matched = 0
        for p in candidates:
            if point_in_polygon(p['geometry'], buffer_poly):
                # Only recognised sound categories become evidence for the
                # segment. Generic Flickr photos inside the buffer are ignored
                # instead of creating artificial "dominant" categories.
                sound_category = p.get('sound_category')
                if sound_category not in category_counts:
                    continue
                category_counts[sound_category] += 1
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
