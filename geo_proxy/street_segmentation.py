"""Street segmentation module for the Chatty Maps Zürich project.

Solves the street segmentation problem (Task 4 in the workflow) by:
  1. Reading street geometries from the streets_ZH.shp shapefile
     (pure-Python parsing, no external GIS dependencies).
  2. Matching street names from the amtliches-strassenverzeichnis CSV
     using nearest-centroid matching.
  3. Filtering to Zürich city streets only.
  4. Cutting long streets into segments of ≤ MAX_SEGMENT_LENGTH metres.
  5. Converting from CH1903+ / LV95 (EPSG:2056) to WGS84 (EPSG:4326).

Coordinate conversion uses the official Swiss approximate formulas
published by swisstopo (accurate to ~1 m, sufficient for our purpose).

References:
    swisstopo, "Approximate solution for the transformation between
    Swiss projection coordinates and WGS84", 2016.
    https://www.swisstopo.admin.ch/en/knowledge-facts/surveying-geodesy/
"""

import csv
import math
from typing import List, Dict, Tuple, Optional

from geo_proxy.shp_parser import read_shp, Polyline


# ---------------------------------------------------------------------------
# Coordinate conversion: CH1903+ / LV95 → WGS84
# ---------------------------------------------------------------------------

def lv95_to_wgs84(east: float, north: float) -> Tuple[float, float]:
    """Convert CH1903+ / LV95 coordinates to WGS84 (lat, lon).

    Uses the official swisstopo approximate formulas.

    Parameters
    ----------
    east : float
        Easting in metres (e.g. 2683000).
    north : float
        Northing in metres (e.g. 1248000).

    Returns
    -------
    Tuple[float, float]
        (latitude, longitude) in decimal degrees (WGS84).
    """
    # Auxiliary values – shift to Bern origin
    y_aux = (east - 2_600_000) / 1_000_000
    x_aux = (north - 1_200_000) / 1_000_000

    # Latitude (arc seconds)
    lat_sec = (16.9023892
               + 3.238272 * x_aux
               - 0.270978 * y_aux ** 2
               - 0.002528 * x_aux ** 2
               - 0.0447 * y_aux ** 2 * x_aux
               - 0.0140 * x_aux ** 3)

    # Longitude (arc seconds)
    lon_sec = (2.6779094
               + 4.728982 * y_aux
               + 0.791484 * y_aux * x_aux
               + 0.1306 * y_aux * x_aux ** 2
               - 0.0436 * y_aux ** 3)

    lat = lat_sec * 100 / 36  # arc seconds → degrees
    lon = lon_sec * 100 / 36

    return lat, lon


# ---------------------------------------------------------------------------
# Euclidean distance in projected coordinates (metres)
# ---------------------------------------------------------------------------

def _dist_2d(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Euclidean distance between two points in projected (metre) space."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _polyline_length(coords: List[Tuple[float, float]]) -> float:
    """Total length of a polyline in projected coordinates."""
    total = 0.0
    for i in range(len(coords) - 1):
        total += _dist_2d(coords[i], coords[i + 1])
    return total


def _polyline_centroid(coords: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Simple centroid (mean of coordinates) of a polyline."""
    n = len(coords)
    if n == 0:
        return (0.0, 0.0)
    cx = sum(c[0] for c in coords) / n
    cy = sum(c[1] for c in coords) / n
    return (cx, cy)


# ---------------------------------------------------------------------------
# Segment cutting
# ---------------------------------------------------------------------------

def cut_polyline(coords: List[Tuple[float, float]],
                 max_length: float) -> List[List[Tuple[float, float]]]:
    """Cut a polyline into pieces no longer than max_length metres.

    Walks along the polyline and interpolates exact split points so that
    segments fit together perfectly with no gaps.

    Parameters
    ----------
    coords : List[Tuple[float, float]]
        Vertex coordinates of the polyline in projected (metre) CRS.
    max_length : float
        Maximum allowed segment length in metres.

    Returns
    -------
    List[List[Tuple[float, float]]]
        List of sub-polylines, each at most max_length metres long.
    """
    total = _polyline_length(coords)
    if total <= max_length:
        return [coords]

    segments: List[List[Tuple[float, float]]] = []
    current_segment: List[Tuple[float, float]] = [coords[0]]
    accumulated = 0.0

    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        seg_len = _dist_2d(p1, p2)

        remaining = seg_len

        while accumulated + remaining > max_length:
            # Distance left in this cut
            cut_dist = max_length - accumulated
            t = cut_dist / remaining if remaining > 0 else 0

            # Interpolated split point
            split_x = current_segment[-1][0] + t * (p2[0] - current_segment[-1][0])
            split_y = current_segment[-1][1] + t * (p2[1] - current_segment[-1][1])
            split_pt = (split_x, split_y)

            current_segment.append(split_pt)
            segments.append(current_segment)

            # Start new segment from split point
            current_segment = [split_pt]
            remaining -= cut_dist
            accumulated = 0.0

        current_segment.append(p2)
        accumulated += remaining

    if len(current_segment) >= 2:
        segments.append(current_segment)

    return segments


# ---------------------------------------------------------------------------
# CSV name lookup
# ---------------------------------------------------------------------------

def load_street_names(csv_path: str) -> List[Dict]:
    """Load street names and centroids from the amtliches Strassenverzeichnis CSV.

    Only returns Zürich city entries.
    """
    entries = []
    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            com_name = row.get('COM_NAME', '')
            if 'rich' not in com_name and 'Zürich' not in com_name:
                # Quick filter: only Zürich
                continue
            try:
                easting = float(row.get('STR_EASTING', 0))
                northing = float(row.get('STR_NORTHING', 0))
                name = row.get('STN_LABEL', 'Unknown')
                entries.append({
                    'name': name,
                    'easting': easting,
                    'northing': northing,
                })
            except (ValueError, TypeError):
                continue
    return entries


def match_street_name(centroid: Tuple[float, float],
                      name_entries: List[Dict],
                      max_dist: float = 500.0) -> str:
    """Find the closest street name to a polyline centroid.

    Parameters
    ----------
    centroid : Tuple[float, float]
        (easting, northing) of the polyline centroid in LV95.
    name_entries : List[Dict]
        Entries from load_street_names().
    max_dist : float
        Maximum matching distance in metres.

    Returns
    -------
    str
        Street name, or 'Unknown' if no match within max_dist.
    """
    best_name = 'Unknown'
    best_dist = max_dist

    for entry in name_entries:
        d = _dist_2d(centroid, (entry['easting'], entry['northing']))
        if d < best_dist:
            best_dist = d
            best_name = entry['name']

    return best_name


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def segment_streets(
    shp_path: str,
    csv_path: str,
    max_segment_length: float = 500.0,
    zurich_bbox: Optional[Tuple[float, float, float, float]] = None,
) -> List[Dict]:
    """Full street segmentation pipeline.

    1. Read polylines from the shapefile.
    2. Filter to Zürich area using a bounding box in LV95.
    3. Match street names from the CSV.
    4. Cut each street into segments ≤ max_segment_length metres.
    5. Convert to WGS84.

    Parameters
    ----------
    shp_path : str
        Path to streets_ZH.shp.
    csv_path : str
        Path to amtliches-strassenverzeichnis_ch_2056.csv.
    max_segment_length : float
        Maximum segment length in metres (default 500).
    zurich_bbox : Optional[Tuple[float, float, float, float]]
        (min_east, min_north, max_east, max_north) in LV95.
        Defaults to central Zürich.

    Returns
    -------
    List[Dict]
        Each dict has keys:
          street_name, segment_id, total_segments, length_m,
          start_lat, start_lon, end_lat, end_lon,
          coords_wgs84 (list of (lat, lon) tuples for the full polyline)
    """
    if zurich_bbox is None:
        # Central Zürich in LV95 (generous bounding box)
        zurich_bbox = (2676000, 1241000, 2690000, 1256000)

    min_e, min_n, max_e, max_n = zurich_bbox

    print("Reading shapefile ...")
    polylines = read_shp(shp_path)
    print(f"  {len(polylines):,} polylines read from shapefile.")

    # Filter to Zürich bounding box
    zurich_polylines = []
    for pl in polylines:
        # Flatten all parts into one coordinate list
        all_coords = [c for part in pl for c in part]
        if not all_coords:
            continue
        cx, cy = _polyline_centroid(all_coords)
        if min_e <= cx <= max_e and min_n <= cy <= max_n:
            zurich_polylines.append(all_coords)

    print(f"  {len(zurich_polylines):,} polylines in Zürich bbox.")

    # Load street names
    print("Loading street names from CSV ...")
    name_entries = load_street_names(csv_path)
    print(f"  {len(name_entries):,} Zürich street name entries loaded.")

    # Match names and segment
    print("Segmenting streets ...")
    results = []

    for pl_coords in zurich_polylines:
        centroid = _polyline_centroid(pl_coords)
        street_name = match_street_name(centroid, name_entries)

        segments = cut_polyline(pl_coords, max_segment_length)

        for seg_id, seg_coords in enumerate(segments, start=1):
            # Convert all coords to WGS84
            wgs_coords = [lv95_to_wgs84(e, n) for e, n in seg_coords]

            start_lat, start_lon = wgs_coords[0]
            end_lat, end_lon = wgs_coords[-1]
            length_m = _polyline_length(seg_coords)

            results.append({
                'street_name': street_name,
                'segment_id': seg_id,
                'total_segments': len(segments),
                'length_m': round(length_m, 1),
                'start_lat': round(start_lat, 7),
                'start_lon': round(start_lon, 7),
                'end_lat': round(end_lat, 7),
                'end_lon': round(end_lon, 7),
                'coords_wgs84': wgs_coords,
            })

    print(f"  {len(results):,} segments created.")
    return results


def save_segments_csv(segments: List[Dict], output_path: str) -> None:
    """Save segmented streets to CSV."""
    fieldnames = [
        'street_name', 'segment_id', 'total_segments', 'length_m',
        'start_lat', 'start_lon', 'end_lat', 'end_lon',
    ]
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for seg in segments:
            row = {k: seg[k] for k in fieldnames}
            writer.writerow(row)
    print(f"Saved {len(segments)} segments to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    segs = segment_streets(
        shp_path='streets_ZH.shp',
        csv_path='amtliches-strassenverzeichnis_ch_2056.csv',
        max_segment_length=500.0,
    )
    save_segments_csv(segs, 'data/zurich_street_segments.csv')

    # Print summary
    unique_streets = set(s['street_name'] for s in segs)
    print(f"\nSummary:")
    print(f"  Unique streets: {len(unique_streets)}")
    print(f"  Total segments: {len(segs)}")
    print(f"  Streets split into >1 segment: "
          f"{sum(1 for s in segs if s['total_segments'] > 1 and s['segment_id'] == 1)}")

    # Top 5 longest
    from collections import defaultdict
    street_lengths = defaultdict(float)
    for s in segs:
        street_lengths[s['street_name']] += s['length_m']
    top5 = sorted(street_lengths.items(), key=lambda x: -x[1])[:5]
    print("\nTop 5 longest streets (total length):")
    for name, length in top5:
        print(f"  {name}: {length:.0f} m")
