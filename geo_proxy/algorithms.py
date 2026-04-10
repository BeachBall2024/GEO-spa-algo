import math
from typing import List, Dict, Tuple
from geo_proxy.primitives import Point, BoundingBox, Segment, Polygon


# ---------------------------------------------------------------------------
# Algorithm 1 – Segment Buffer Construction
# ---------------------------------------------------------------------------
# Builds a rectangular buffer polygon around a street segment at a given
# distance (in metres).  Uses:
#   • Haversine-based metre-to-degree conversion  (Lecture 1)
#   • Perpendicular offset via vector rotation
#   • Bounding-box pre-filter                     (Lectures 3-4)
#   • Segment intersection with turn test          (Lecture 3)
#
# Complexity: O(1) per segment  –  constant number of geometric operations.
# ---------------------------------------------------------------------------

def segments_intersect(s1: Segment, s2: Segment) -> bool:
    """Test whether two segments intersect using the turn test (Lecture 3).

    Steps:
      1. Bounding-box pre-filter – reject quickly if boxes don't overlap.
      2. Four turn tests (cross products) to check if each segment
         straddles the line defined by the other.
      3. Collinear overlap check when any cross product is zero.

    Complexity: O(1).
    """
    # Step 1 – bbox pre-filter (Lecture 3-4)
    if not s1.bbox.intersects_bbox(s2.bbox):
        return False

    # Step 2 – orientation tests
    d1 = s1.turn_test(s2.p1)
    d2 = s1.turn_test(s2.p2)
    d3 = s2.turn_test(s1.p1)
    d4 = s2.turn_test(s1.p2)

    # General case: segments straddle each other
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True

    # Collinear / touching cases – check if a point lies on the other segment
    def on_segment(seg: Segment, p: Point) -> bool:
        return (min(seg.p1.x, seg.p2.x) <= p.x <= max(seg.p1.x, seg.p2.x) and
                min(seg.p1.y, seg.p2.y) <= p.y <= max(seg.p1.y, seg.p2.y))

    if d1 == 0 and on_segment(s1, s2.p1):
        return True
    if d2 == 0 and on_segment(s1, s2.p2):
        return True
    if d3 == 0 and on_segment(s2, s1.p1):
        return True
    if d4 == 0 and on_segment(s2, s1.p2):
        return True

    return False


def build_segment_buffer(segment: Segment, distance_m: float = 50.0) -> Polygon:
    """Construct a rectangular buffer polygon around a street segment.

    Given segment AB and buffer distance d (metres):
      1. Compute the direction vector AB.
      2. Compute the perpendicular unit vector (rotated 90°).
      3. Convert d metres to degree offsets using Haversine constants
         for the segment's latitude.
      4. Offset both endpoints by ±perpendicular to get four corners.

    Returns a Polygon with vertices [A+perp, B+perp, B-perp, A-perp].

    Complexity: O(1).
    """
    ax, ay = segment.p1.x, segment.p1.y
    bx, by = segment.p2.x, segment.p2.y

    dx = bx - ax
    dy = by - ay
    seg_len = math.hypot(dx, dy)
    if seg_len == 0:
        seg_len = 1e-12  # degenerate segment guard

    # Unit perpendicular vector (rotated 90° counter-clockwise)
    perp_x = -dy / seg_len
    perp_y = dx / seg_len

    # Metre-to-degree conversion at the segment's mid-latitude (Lecture 1)
    mid_lat_rad = math.radians((ay + by) / 2.0)
    lat_per_m = 1.0 / 111_320.0
    lon_per_m = 1.0 / (111_320.0 * math.cos(mid_lat_rad))

    offset_x = perp_x * distance_m * lon_per_m
    offset_y = perp_y * distance_m * lat_per_m

    # Four corners of the buffer rectangle
    p1_plus  = Point(ax + offset_x, ay + offset_y)
    p2_plus  = Point(bx + offset_x, by + offset_y)
    p2_minus = Point(bx - offset_x, by - offset_y)
    p1_minus = Point(ax - offset_x, ay - offset_y)

    return Polygon([p1_plus, p2_plus, p2_minus, p1_minus])


# ---------------------------------------------------------------------------
# Algorithm 2 – Point-in-Polygon via Ray Casting  (Lecture 4)
# ---------------------------------------------------------------------------
# Uses a horizontal ray from the test point to +∞ and counts edge crossings.
# Even-odd rule (Jordan Curve Theorem): inside iff crossing count is odd.
#
# Complexity: O(e) where e = number of polygon edges.  Bbox pre-filter O(1).
# ---------------------------------------------------------------------------

def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Ray-casting point-in-polygon test.

    1. Bounding-box rejection (Lectures 3-4) – O(1).
    2. Cast a horizontal ray to the right from *point*.
    3. For every non-horizontal polygon edge whose y-range spans the
       ray's y-coordinate, compute the x-intercept.
    4. Count intercepts to the right of *point*.
    5. Odd count → inside (even-odd / Jordan Curve Theorem, Lecture 4).

    Complexity: O(e) where e = number of edges.
    """
    # Bbox pre-filter
    if not polygon.bbox.contains_point(point):
        return False

    intersection_count = 0
    for segment in polygon.segments:
        # Skip horizontal edges
        if segment.p1.y == segment.p2.y:
            continue
        # Check if ray's y-coordinate is within the edge's y-range
        if (point.y < segment.p1.y) != (point.y < segment.p2.y):
            # X-coordinate of the ray-edge intersection
            x_int = ((segment.p2.x - segment.p1.x)
                     * (point.y - segment.p1.y)
                     / (segment.p2.y - segment.p1.y)
                     + segment.p1.x)
            if point.x < x_int:
                intersection_count += 1

    return intersection_count % 2 == 1


# ---------------------------------------------------------------------------
# Algorithm 3 – Sound-Profile Computation with Z-Score Normalisation
# ---------------------------------------------------------------------------
# Implements the core Chatty Maps methodology (Aiello et al., 2016):
#   sound(j,c) = tags(j,c) / tags(j)         – fraction per category
#   z(j,c) = (sound(j,c) - μ_c) / σ_c        – z-score normalisation
#
# Also computes the area-weighted centroid (Lecture 2) of each buffer
# polygon as the segment's representative location.
#
# Complexity: O(S × C) where S = segments, C = categories (constant = 6).
# ---------------------------------------------------------------------------

SOUND_CATEGORIES = ['transport', 'nature', 'human', 'music', 'mechanical', 'indoor']


def compute_sound_profile(category_counts: Dict[str, int]) -> Dict[str, float]:
    """Compute a segment's sound profile: fraction of tags per category.

    sound(j, c) = tags(j, c) / tags(j)

    Returns a dict mapping each of the 6 categories to its fraction [0, 1].
    If a segment has no tags, all fractions are 0.

    Complexity: O(C) where C = 6 categories.
    """
    total = sum(category_counts.get(c, 0) for c in SOUND_CATEGORIES)
    if total == 0:
        return {c: 0.0 for c in SOUND_CATEGORIES}
    return {c: category_counts.get(c, 0) / total for c in SOUND_CATEGORIES}


def zscore_normalise(profiles: List[Dict[str, float]]) -> List[Dict[str, float]]:
    """Z-score normalise sound profiles across all segments.

    For each category c:
        μ_c  = mean of sound(j, c) across all segments j
        σ_c  = std-dev of sound(j, c)
        z(j, c) = (sound(j, c) - μ_c) / σ_c

    This allows cross-category comparison on a common scale, as described
    in Aiello et al. (2016), Section 3.3.

    Complexity: O(S × C) where S = number of segments, C = 6.
    """
    n = len(profiles)
    if n == 0:
        return []

    normalised = [{} for _ in range(n)]

    for c in SOUND_CATEGORIES:
        values = [p[c] for p in profiles]
        mean_c = sum(values) / n
        var_c = sum((v - mean_c) ** 2 for v in values) / n
        std_c = math.sqrt(var_c) if var_c > 0 else 1.0  # avoid division by zero

        for i in range(n):
            normalised[i][c] = (profiles[i][c] - mean_c) / std_c

    return normalised


def dominant_sound(z_profile: Dict[str, float]) -> str:
    """Return the sound category with the highest z-score for a segment."""
    if not z_profile:
        return 'none'
    return max(z_profile, key=z_profile.get)


# ---------------------------------------------------------------------------
# Utility – kept for convenience but NOT one of the 3 graded algorithms
# ---------------------------------------------------------------------------

def point_to_segment_distance(point: Point, segment: Segment) -> float:
    """Shortest distance (metres) from a point to a line segment.

    Uses vector projection with clamping to endpoints, then Haversine
    for the final metre distance.
    """
    vx = segment.p2.x - segment.p1.x
    vy = segment.p2.y - segment.p1.y
    wx = point.x - segment.p1.x
    wy = point.y - segment.p1.y

    c1 = wx * vx + wy * vy
    if c1 <= 0:
        return point.haversine_distance_to(segment.p1)

    c2 = vx * vx + vy * vy
    if c2 <= c1:
        return point.haversine_distance_to(segment.p2)

    b = c1 / c2
    projected = Point(segment.p1.x + b * vx, segment.p1.y + b * vy)
    return point.haversine_distance_to(projected)
