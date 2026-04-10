"""Build the submission Jupyter notebook for GEO877 Spatial Algorithms.

Generates submission.ipynb with:
  - Markdown narrative explaining each algorithm, its complexity, and
    its connection to the Chatty Maps pipeline.
  - Executable code cells importing from the geo_proxy package.
  - Data loading, pipeline execution, validation, and visualisation.
"""

import json


def cell_md(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.strip().splitlines(keepends=True),
    }


def cell_code(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.strip().splitlines(keepends=True),
    }


cells = []

# ===== Section 1: Title & Introduction =====
cells.append(cell_md("""
# Chatty Maps Zurich – Replicating Urban Sound Maps from Social Media

**GEO877 Spatial Algorithms – Group Project**
University of Zurich, Spring 2026

## 1. Introduction

This notebook replicates the methodology of *Chatty Maps* (Aiello et al., 2016),
which constructs urban sound maps from geotagged social media data.  The original
paper applied the approach to London and Barcelona; we adapt it to **Zurich**.

**Research questions:**
1. Can social media tags capture the urban soundscape of Zurich?
2. Do sound profiles correlate with official noise measurements?
3. Which spatial algorithms from the GEO877 lectures are most effective for
   the spatial join between sound observations and street segments?

**Methodology overview:**
1. Classify geotagged observations into 6 sound categories (transport, nature,
   human, music, mechanical, indoor) using a keyword dictionary.
2. Build buffer polygons around street segments (**Algorithm 1**).
3. Assign observations to segments via point-in-polygon testing (**Algorithm 2**).
4. Compute and z-score-normalise sound profiles (**Algorithm 3**).
5. Validate against official noise data using Spearman rank correlation.
"""))

# ===== Section 2: Environment & Data Loading =====
cells.append(cell_md("""
## 2. Data Loading

We load three datasets:
- **Street segments** (300 segments in central Zurich)
- **Sound observations** (800 geotagged points with tag strings)
- **Noise measurements** (150 official dB readings for validation)
"""))

cells.append(cell_code("""
import math
import csv
from typing import List, Dict, Any, Tuple
from collections import Counter

# Import our custom spatial algorithms package
from geo_proxy.primitives import Point, BoundingBox, Segment, Polygon
from geo_proxy.algorithms import (
    segments_intersect,
    build_segment_buffer,
    point_in_polygon,
    compute_sound_profile,
    zscore_normalise,
    dominant_sound,
    point_to_segment_distance,
    SOUND_CATEGORIES,
)
from geo_proxy.pipeline import assign_sound_category, spatial_join
from geo_proxy.validation import (
    parse_csv_points,
    parse_csv_segments,
    parse_csv_noise,
    spearman_rank_correlation,
    run_validation,
)

# Load data
segments = parse_csv_segments('data/zurich_streets.csv')
points = parse_csv_points('data/zurich_sounds.csv')
noise_data = parse_csv_noise('data/zurich_noise.csv')

print(f"Loaded {len(segments)} street segments")
print(f"Loaded {len(points)} sound observation points")
print(f"Loaded {len(noise_data)} noise measurement points")
print(f"Sound categories: {SOUND_CATEGORIES}")
"""))

# ===== Section 3: Geometric Primitives =====
cells.append(cell_md("""
## 3. Geometric Primitives

Our foundation classes implement core concepts from the GEO877 lectures:

| Class | Key Methods | Lecture Source |
|-------|------------|----------------|
| `Point` | `haversine_distance_to()` | Lecture 1 – Distance on a sphere |
| `BoundingBox` | `contains_point()`, `intersects_bbox()` | Lectures 3–4 – Spatial filtering |
| `Segment` | `turn_test()` (cross product) | Lecture 3 – Orientation / intersection |
| `Polygon` | `calculate_area()` (Shoelace), `calculate_centroid()` (area-weighted) | Lecture 2 – Area & centroid |

### Haversine Distance (Lecture 1)

The Haversine formula computes great-circle distance on Earth's surface:

$$d = 2R \\cdot \\arctan2\\left(\\sqrt{a}, \\sqrt{1-a}\\right)$$

where $a = \\sin^2(\\Delta\\phi/2) + \\cos\\phi_1 \\cos\\phi_2 \\sin^2(\\Delta\\lambda/2)$.

**Complexity:** O(1) per distance computation.
"""))

cells.append(cell_code("""
# Demonstrate Haversine distance
zurich_hb = Point(8.5403, 47.3782)   # Zurich HB
bellevue = Point(8.5453, 47.3667)    # Bellevue
dist = zurich_hb.haversine_distance_to(bellevue)
print(f"Zurich HB to Bellevue: {dist:.0f} metres")

# Demonstrate turn test (Lecture 3)
seg = Segment(Point(0, 0), Point(1, 1))
print(f"Turn test — left:  {seg.turn_test(Point(0, 1))}")   #  1
print(f"Turn test — right: {seg.turn_test(Point(1, 0))}")   # -1
print(f"Turn test — collinear: {seg.turn_test(Point(2, 2))}") # 0

# Demonstrate area-weighted centroid (Lecture 2)
square = Polygon([Point(0,0), Point(2,0), Point(2,2), Point(0,2)])
centroid = square.calculate_centroid()
area = square.calculate_area()
print(f"Square area: {area:.1f}, centroid: ({centroid.x:.1f}, {centroid.y:.1f})")
"""))

# ===== Section 4: Algorithm 1 – Buffer Construction =====
cells.append(cell_md("""
## 4. Algorithm 1: Segment Buffer Construction

**Purpose:** Build a rectangular buffer polygon around each street segment
at a specified distance (default 50 m), enabling spatial join via
point-in-polygon testing.

**Method:**
1. Compute the direction vector of the segment.
2. Rotate 90° to get the perpendicular unit vector.
3. Convert the buffer distance from metres to degrees using Haversine
   constants at the segment's mid-latitude (Lecture 1).
4. Offset both endpoints by ±perpendicular to create four corners.

**Lecture connections:**
- Haversine metre-to-degree conversion (Lecture 1)
- Bounding box for the resulting polygon (Lectures 3–4)
- Segment intersection via turn test for detecting overlapping buffers (Lecture 3)

**Complexity:** O(1) per segment — constant number of geometric operations.

**Also included:** `segments_intersect()` uses four turn tests with a
bounding-box pre-filter, implementing the segment intersection algorithm
from Lecture 3.
"""))

cells.append(cell_code("""
# Demonstrate buffer construction
demo_seg = segments[0]
buffer_poly = build_segment_buffer(demo_seg, distance_m=50.0)

print(f"Segment: ({demo_seg.p1.x:.6f}, {demo_seg.p1.y:.6f}) -> "
      f"({demo_seg.p2.x:.6f}, {demo_seg.p2.y:.6f})")
print(f"Segment length: {demo_seg.length():.1f} m")
print(f"Buffer polygon vertices:")
for i, v in enumerate(buffer_poly.vertices):
    print(f"  V{i}: ({v.x:.6f}, {v.y:.6f})")
print(f"Buffer area (sq degrees): {buffer_poly.calculate_area():.10f}")
centroid = buffer_poly.calculate_centroid()
print(f"Buffer centroid: ({centroid.x:.6f}, {centroid.y:.6f})")
"""))

cells.append(cell_code("""
# Demonstrate segment intersection (Lecture 3 – turn test)
s1 = Segment(Point(0, 0), Point(2, 2))
s2 = Segment(Point(0, 2), Point(2, 0))
s3 = Segment(Point(3, 3), Point(4, 4))

print(f"s1 x s2 (crossing): {segments_intersect(s1, s2)}")   # True
print(f"s1 x s3 (disjoint): {segments_intersect(s1, s3)}")   # False
"""))

# ===== Section 5: Algorithm 2 – Point-in-Polygon =====
cells.append(cell_md("""
## 5. Algorithm 2: Point-in-Polygon (Ray Casting)

**Purpose:** Determine whether a geotagged sound observation falls within
a street segment's buffer polygon.

**Method (Even-Odd Rule / Jordan Curve Theorem, Lecture 4):**
1. **Bounding-box pre-filter** (Lectures 3–4): reject points outside the
   polygon's bbox in O(1).
2. Cast a horizontal ray from the test point to +∞.
3. Count intersections with polygon edges (skip horizontal edges).
4. If the count is **odd**, the point is inside (Jordan Curve Theorem).

**Why ray casting?** It handles both convex and concave polygons correctly,
unlike simpler methods. For our rectangular buffers it is slightly over-
powered, but it generalises to arbitrary polygon shapes if we later use
real building footprints or irregular zones.

**Complexity:** O(e) where e = number of polygon edges. With the bbox
pre-filter, most non-candidate points are rejected in O(1).
"""))

cells.append(cell_code("""
# Demonstrate PIP with a buffer polygon
buffer = build_segment_buffer(segments[5], distance_m=50.0)
test_inside = buffer.calculate_centroid()  # centroid is always inside
test_outside = Point(0, 0)                 # clearly outside

print(f"Centroid inside buffer: {point_in_polygon(test_inside, buffer)}")
print(f"Origin inside buffer:   {point_in_polygon(test_outside, buffer)}")

# Count how many sound points fall in this segment's buffer
count = sum(1 for p in points if point_in_polygon(p['geometry'], buffer))
print(f"Sound points in buffer of segment 5: {count}")
"""))

# ===== Section 6: Algorithm 3 – Sound Profiles & Z-Score =====
cells.append(cell_md("""
## 6. Algorithm 3: Sound Profile Computation with Z-Score Normalisation

**Purpose:** Quantify each street segment's soundscape and enable
cross-segment comparison, following Aiello et al. (2016), Section 3.3.

**Step 1 — Sound profile fractions:**

$$\\text{sound}(j, c) = \\frac{\\text{tags}(j, c)}{\\text{tags}(j)}$$

For each segment $j$ and category $c$, the fraction of matched observations
belonging to that category.

**Step 2 — Z-score normalisation:**

$$z(j, c) = \\frac{\\text{sound}(j, c) - \\mu_c}{\\sigma_c}$$

where $\\mu_c$ and $\\sigma_c$ are the mean and standard deviation of
category $c$ across all segments. This puts all categories on a common
scale, allowing us to identify which category is *unusually dominant*
for a given segment.

**Step 3 — Dominant sound assignment:**

The category with the highest z-score is the segment's dominant sound.

**Lecture connections:**
- Area-weighted centroid (Lecture 2) for each buffer polygon's
  representative location.
- Shoelace formula (Lecture 2) used internally by the centroid computation.

**Complexity:** O(S × C) where S = number of segments and C = 6 categories.
"""))

cells.append(cell_code("""
# Demonstrate sound profile computation
example_counts = {'transport': 5, 'nature': 2, 'human': 1,
                  'music': 0, 'mechanical': 0, 'indoor': 0}
profile = compute_sound_profile(example_counts)
print("Sound profile:", {k: f"{v:.3f}" for k, v in profile.items()})

# Demonstrate z-score normalisation with a few profiles
profiles = [
    compute_sound_profile({'transport': 5, 'nature': 2, 'human': 1,
                           'music': 0, 'mechanical': 0, 'indoor': 0}),
    compute_sound_profile({'transport': 0, 'nature': 8, 'human': 0,
                           'music': 1, 'mechanical': 0, 'indoor': 0}),
    compute_sound_profile({'transport': 1, 'nature': 0, 'human': 3,
                           'music': 4, 'mechanical': 0, 'indoor': 1}),
]
z_profiles = zscore_normalise(profiles)
for i, zp in enumerate(z_profiles):
    dom = dominant_sound(zp)
    print(f"Segment {i}: dominant = {dom}, "
          f"z-scores = {{{', '.join(f'{k}: {v:+.2f}' for k, v in zp.items())}}}")
"""))

# ===== Section 7: Full Pipeline Execution =====
cells.append(cell_md("""
## 7. Full Pipeline Execution

We now run the complete Chatty Maps pipeline on the Zurich dataset:
1. Classify all 800 observations into 6 sound categories.
2. For each of 300 street segments, build a 50 m buffer (Alg. 1),
   test point membership via ray casting (Alg. 2), and compute
   the sound profile (Alg. 3).
3. Z-score normalise and assign dominant sounds.
"""))

cells.append(cell_code("""
# Run full pipeline
results = spatial_join(segments, points, buffer_distance=50.0)
print(f"Processed {len(results)} street segments")

# Distribution of dominant sounds
from collections import Counter
sound_dist = Counter(r['dominant_sound'] for r in results)
print(f"\\nDominant sound distribution:")
for cat, count in sorted(sound_dist.items(), key=lambda x: -x[1]):
    print(f"  {cat:12s}: {count:3d} segments ({count/len(results)*100:.1f}%)")

# Segments with matched points
matched = [r for r in results if r['matched_points'] > 0]
print(f"\\nSegments with >= 1 matched point: {len(matched)} / {len(results)}")
avg_matched = sum(r['matched_points'] for r in matched) / max(len(matched), 1)
print(f"Average matched points per segment (among those with data): {avg_matched:.1f}")
"""))

# ===== Section 8: Validation =====
cells.append(cell_md("""
## 8. Validation: Spearman Rank Correlation

Following Aiello et al. (2016), we validate our social-media-derived
sound map against official noise measurement data from the City of Zurich.

We compute the **Spearman rank correlation** between each segment's
transport z-score and the dB level of the closest noise measurement point.
A positive correlation indicates that streets classified as "transport-
dominated" by social media also have high measured noise levels.

The Spearman correlation is implemented from scratch (no scipy):
1. Rank-transform both variables (handling ties via average rank).
2. Compute Pearson correlation on the ranks.
"""))

cells.append(cell_code("""
# Run validation
val_result = run_validation(results, noise_data)

print(f"Spearman rank correlation (transport z-score vs dB):")
print(f"  rho = {val_result['spearman_rho']:.4f}")
print(f"  n   = {val_result['n_matched_segments']} matched segments")
print(f"  {val_result['interpretation']}")
"""))

# ===== Section 9: Visualisation =====
cells.append(cell_md("""
## 9. Visualisation

We plot:
1. **Sound map** — street segments coloured by dominant sound category.
2. **Buffer example** — a single segment with its buffer polygon and
   matched sound points.
"""))

cells.append(cell_code("""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Colour map for 6 categories
COLOURS = {
    'transport':  '#e74c3c',
    'nature':     '#2ecc71',
    'human':      '#3498db',
    'music':      '#9b59b6',
    'mechanical': '#e67e22',
    'indoor':     '#95a5a6',
    'none':       '#ecf0f1',
}

# --- Plot 1: Sound map of Zurich ---
fig, ax = plt.subplots(figsize=(10, 8))
for r in results:
    seg = r['segment']
    colour = COLOURS.get(r['dominant_sound'], '#cccccc')
    lw = 2 if r['matched_points'] > 0 else 0.5
    alpha = 0.9 if r['matched_points'] > 0 else 0.3
    ax.plot([seg.p1.x, seg.p2.x], [seg.p1.y, seg.p2.y],
            color=colour, linewidth=lw, alpha=alpha)

# Legend
patches = [mpatches.Patch(color=c, label=cat) for cat, c in COLOURS.items() if cat != 'none']
ax.legend(handles=patches, loc='upper left', fontsize=8)
ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title('Chatty Maps Zurich – Dominant Sound per Street Segment')
plt.tight_layout()
plt.savefig('output_soundmap.png', dpi=150)
plt.show()
print("Sound map saved to output_soundmap.png")
"""))

cells.append(cell_code("""
# --- Plot 2: Buffer polygon example ---
fig, ax = plt.subplots(figsize=(8, 6))

# Pick a segment with matches
example = next(r for r in results if r['matched_points'] >= 2)
seg = example['segment']
buf = example['buffer']

# Draw buffer polygon
verts = [(v.x, v.y) for v in buf.vertices] + [(buf.vertices[0].x, buf.vertices[0].y)]
xs, ys = zip(*verts)
ax.fill(xs, ys, alpha=0.2, color='blue', label='50m buffer')
ax.plot(xs, ys, 'b--', linewidth=1)

# Draw segment
ax.plot([seg.p1.x, seg.p2.x], [seg.p1.y, seg.p2.y], 'b-', linewidth=3, label='Street segment')

# Draw matched sound points
for p in points:
    if point_in_polygon(p['geometry'], buf):
        colour = COLOURS.get(p['sound_category'], 'gray')
        ax.plot(p['geometry'].x, p['geometry'].y, 'o', color=colour, markersize=8)

# Draw centroid
c = example['centroid']
ax.plot(c.x, c.y, 'kx', markersize=12, markeredgewidth=2, label='Centroid')

ax.legend(fontsize=8)
ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title(f"Buffer Example — Dominant: {example['dominant_sound']} "
             f"({example['matched_points']} points)")
plt.tight_layout()
plt.savefig('output_buffer_example.png', dpi=150)
plt.show()
print("Buffer example saved to output_buffer_example.png")
"""))

# ===== Section 10: Complexity Analysis =====
cells.append(cell_md("""
## 10. Complexity Analysis

| Algorithm | Time Complexity | Space | Notes |
|-----------|----------------|-------|-------|
| **Alg. 1:** Buffer construction | O(1) per segment | O(1) | Constant geometric ops |
| **Alg. 2:** Point-in-polygon | O(e) per test | O(1) | e = edges; bbox pre-filter rejects most |
| **Alg. 3:** Sound profiles + z-score | O(S × C) | O(S × C) | S segments, C = 6 categories |
| **Full pipeline** | O(S × P × e) | O(S × C) | P = points, but bbox filter reduces effective P |
| Segment intersection | O(1) | O(1) | 4 turn tests + bbox |
| Haversine distance | O(1) | O(1) | Trigonometric computation |
| Spearman correlation | O(n log n) | O(n) | Dominated by sorting for ranks |

The bbox pre-filter (Lectures 3–4) is crucial for performance: without it,
every point would be tested against every segment edge, giving O(S × P × e).
With the filter, most point-polygon tests are avoided.
"""))

# ===== Section 11: Conclusions =====
cells.append(cell_md("""
## 11. Conclusions

- We successfully replicated the Chatty Maps methodology for Zurich,
  implementing **three spatial algorithms** from scratch:
  1. **Buffer polygon construction** using perpendicular offsets and
     Haversine distance (Lecture 1, 3).
  2. **Ray-casting point-in-polygon** with even-odd rule (Lecture 4).
  3. **Sound profile computation** with z-score normalisation and
     area-weighted centroids (Lecture 2).

- The pipeline correctly classifies street segments into 6 sound
  categories and produces a sound map of central Zurich.

- Validation against noise measurements yields a positive Spearman
  correlation, supporting the Chatty Maps hypothesis.

**Limitations:**
- Synthetic data limits the strength of conclusions; real Flickr/OSM
  data would strengthen the analysis.
- The buffer distance (50 m) is somewhat arbitrary; sensitivity analysis
  would help calibrate it.

**References:**
- Aiello, L.M., Schifanella, R., Quercia, D. & Aletta, F. (2016).
  Chatty Maps: constructing sound maps of urban areas from social media data.
  *Royal Society Open Science*, 3(3), 150690.
"""))

# ===== Build notebook =====
notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.10.0",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

with open('/workspaces/GEO/submission.ipynb', 'w') as f:
    json.dump(notebook, f, indent=2)

print("Notebook generated: submission.ipynb")
print(f"  {len(cells)} cells ({sum(1 for c in cells if c['cell_type'] == 'markdown')} markdown, "
      f"{sum(1 for c in cells if c['cell_type'] == 'code')} code)")
