"""Generate synthetic data for the Chatty Maps Zurich replication.

Covers a realistic area of central Zurich (Altstadt, Bahnhofstrasse,
Limmatquai, Seefeld) with 6 sound categories and spatially coherent
placement – transport points near known road corridors, nature points
near the lake/Limmat, etc.

Ideally this would be replaced by real data from:
  - OpenStreetMap (Overpass API) for street segments
  - Flickr API / Freesound API for geotagged sound observations
  - Stadt Zürich Open Data for noise dB measurements
"""

import csv
import random
import math

# ---------------------------------------------------------------------------
# Zurich geographic bounds  (central city, ~2.5 km × 1.5 km)
# ---------------------------------------------------------------------------
LAT_MIN, LAT_MAX = 47.365, 47.385
LON_MIN, LON_MAX = 8.525, 8.555

# Approximate zones for spatially coherent placement
ZONES = {
    'transport_corridor': {'lat': (47.370, 47.380), 'lon': (8.530, 8.545)},
    'lake_river':         {'lat': (47.365, 47.372), 'lon': (8.535, 8.550)},
    'old_town':           {'lat': (47.372, 47.378), 'lon': (8.538, 8.545)},
    'residential':        {'lat': (47.378, 47.385), 'lon': (8.528, 8.540)},
}

# Tag templates per category (6 categories – Aiello et al.)
TAG_TEMPLATES = {
    'transport': [
        "car traffic road driving highway",
        "tram train bus public transport",
        "taxi horn engine motor vehicle",
        "motorcycle scooter bicycle road",
        "truck siren traffic highway driving",
    ],
    'nature': [
        "bird water river garden park",
        "tree leaves wind lake grass",
        "flower forest rain sky creek",
        "animal dog park garden bird",
        "bee insect water lake tree",
    ],
    'human': [
        "crowd people talk laugh market",
        "cafe restaurant conversation voice chat",
        "children footsteps cheer applause speech",
        "bar people shout crowd sing",
        "market talk laugh people cafe",
    ],
    'music': [
        "music guitar concert band song",
        "piano jazz classical melody festival",
        "busker drums rock violin flute",
        "choir orchestra trumpet song dj",
        "concert band music festival jazz",
    ],
    'mechanical': [
        "construction drill hammer machine factory",
        "crane jackhammer demolition industrial metal",
        "saw equipment pump generator compressor",
        "welding construction drill machine equipment",
        "factory industrial hammer metal crane",
    ],
    'indoor': [
        "museum library church indoor hall",
        "station airport office elevator door",
        "fan ventilation heating indoor ac",
        "escalator door office hall museum",
        "church library station indoor heating",
    ],
}

# Category distribution weights per zone (controls spatial coherence)
ZONE_WEIGHTS = {
    'transport_corridor': {'transport': 0.45, 'mechanical': 0.15, 'human': 0.15,
                           'music': 0.05, 'nature': 0.10, 'indoor': 0.10},
    'lake_river':         {'nature': 0.50, 'human': 0.15, 'transport': 0.10,
                           'music': 0.10, 'mechanical': 0.05, 'indoor': 0.10},
    'old_town':           {'human': 0.30, 'music': 0.20, 'indoor': 0.20,
                           'transport': 0.15, 'nature': 0.10, 'mechanical': 0.05},
    'residential':        {'human': 0.25, 'nature': 0.20, 'transport': 0.20,
                           'indoor': 0.15, 'mechanical': 0.10, 'music': 0.10},
}


def _weighted_choice(weights: dict) -> str:
    categories = list(weights.keys())
    cumulative = []
    total = 0.0
    for c in categories:
        total += weights[c]
        cumulative.append(total)
    r = random.random() * total
    for i, threshold in enumerate(cumulative):
        if r <= threshold:
            return categories[i]
    return categories[-1]


def _random_in_zone(zone: dict) -> tuple:
    lat = random.uniform(*zone['lat'])
    lon = random.uniform(*zone['lon'])
    return lat, lon


def generate_street_segments(n: int = 300) -> list:
    """Generate realistic street segments within Zurich bounds."""
    segments = []
    for i in range(1, n + 1):
        # Pick a random start point
        lat = random.uniform(LAT_MIN, LAT_MAX)
        lon = random.uniform(LON_MIN, LON_MAX)
        # Street segments are typically 50-200 m long
        length_deg = random.uniform(0.0005, 0.002)
        angle = random.uniform(0, 2 * math.pi)
        end_lat = lat + length_deg * math.sin(angle)
        end_lon = lon + length_deg * math.cos(angle)
        # Clamp to bounds
        end_lat = max(LAT_MIN, min(LAT_MAX, end_lat))
        end_lon = max(LON_MIN, min(LON_MAX, end_lon))
        segments.append({
            'segment_id': f'street_{i}',
            'street_name': f'Zurich_Street_{i}',
            'start_lat': round(lat, 6),
            'start_lon': round(lon, 6),
            'end_lat': round(end_lat, 6),
            'end_lon': round(end_lon, 6),
        })
    return segments


def generate_sound_points(n: int = 800) -> list:
    """Generate geotagged sound observations with spatially coherent categories."""
    zone_names = list(ZONES.keys())
    points = []
    for i in range(1, n + 1):
        # Pick a zone at random
        zone_name = random.choice(zone_names)
        zone = ZONES[zone_name]
        lat, lon = _random_in_zone(zone)
        # Pick category weighted by zone
        category = _weighted_choice(ZONE_WEIGHTS[zone_name])
        tags = random.choice(TAG_TEMPLATES[category])
        points.append({
            'id': f'poi_{i}',
            'lat': round(lat, 6),
            'lon': round(lon, 6),
            'tags': tags,
        })
    return points


def generate_noise_data(n: int = 150) -> list:
    """Generate synthetic noise measurement data (dB levels).

    Transport corridors get higher dB, nature/lake areas get lower dB.
    """
    data = []
    for i in range(1, n + 1):
        zone_name = random.choice(list(ZONES.keys()))
        zone = ZONES[zone_name]
        lat, lon = _random_in_zone(zone)
        # Base dB depends on zone
        base_db = {
            'transport_corridor': 72,
            'old_town': 62,
            'residential': 55,
            'lake_river': 48,
        }[zone_name]
        db = round(base_db + random.gauss(0, 5), 1)
        data.append({
            'id': f'noise_{i}',
            'lat': round(lat, 6),
            'lon': round(lon, 6),
            'db_level': db,
        })
    return data


def main():
    random.seed(42)  # reproducibility

    print("Generating street segments...")
    segments = generate_street_segments(300)
    with open('/workspaces/GEO/data/zurich_streets.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=segments[0].keys())
        writer.writeheader()
        writer.writerows(segments)

    print("Generating sound observation points (6 categories)...")
    points = generate_sound_points(800)
    with open('/workspaces/GEO/data/zurich_sounds.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=points[0].keys())
        writer.writeheader()
        writer.writerows(points)

    print("Generating noise measurement data...")
    noise = generate_noise_data(150)
    with open('/workspaces/GEO/data/zurich_noise.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=noise[0].keys())
        writer.writeheader()
        writer.writerows(noise)

    print(f"Done: {len(segments)} segments, {len(points)} sound points, "
          f"{len(noise)} noise measurements.")


if __name__ == '__main__':
    main()
