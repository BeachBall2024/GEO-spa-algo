"""Generate the final Contextily basemap plot.

The main pipeline writes ``data/pipeline_results.csv``. This script reads that
table, recreates the custom ``geo_proxy.primitives.Segment`` objects and plots
them over CartoDB Positron tiles.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Iterable, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import contextily as cx

from geo_proxy.algorithms import SOUND_CATEGORIES
from submission_script import (
    CATEGORY_COLORS,
    DEFAULT_PLOTS_DIR,
    DEFAULT_RESULTS,
    NO_DATA_COLOR,
    PROJECT_ROOT,
    load_results_csv,
)


WEB_MERCATOR_RADIUS = 6_378_137.0


def _resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def lonlat_to_web_mercator(lon: float, lat: float) -> Tuple[float, float]:
    """Convert WGS84 longitude/latitude to EPSG:3857 metres."""
    # Clamp latitude to the valid Web Mercator range.
    lat = max(min(lat, 85.05112878), -85.05112878)
    x = WEB_MERCATOR_RADIUS * math.radians(lon)
    y = WEB_MERCATOR_RADIUS * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    return x, y


def _legend_handles() -> Sequence[Line2D]:
    handles = [
        Line2D([0], [0], color=CATEGORY_COLORS[category], lw=4, label=category)
        for category in SOUND_CATEGORIES
    ]
    handles.append(Line2D([0], [0], color=NO_DATA_COLOR, lw=3, label="no data"))
    return handles


def _segment_xy(result: Dict) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Return projected start/end coordinates for a custom Segment result."""
    segment = result["segment"]
    start = lonlat_to_web_mercator(segment.p1.x, segment.p1.y)
    end = lonlat_to_web_mercator(segment.p2.x, segment.p2.y)
    return start, end


def plot_basemap(results: Sequence[Dict], output_path: Path) -> None:
    if not results:
        raise ValueError("No results available for basemap plotting.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 12))

    projected_bounds = []
    ordered = sorted(results, key=lambda r: r.get("dominant_sound") != "none")
    for result in ordered:
        (x1, y1), (x2, y2) = _segment_xy(result)
        projected_bounds.extend([(x1, y1), (x2, y2)])
        category = result.get("dominant_sound", "none")
        color = CATEGORY_COLORS.get(category, NO_DATA_COLOR)
        linewidth = 3.0 if category != "none" else 0.5
        alpha = 0.95 if category != "none" else 0.25
        zorder = 3 if category != "none" else 2
        ax.plot(
            [x1, x2],
            [y1, y2],
            color=color,
            linewidth=linewidth,
            alpha=alpha,
            solid_capstyle="round",
            zorder=zorder,
        )

    xs = [point[0] for point in projected_bounds]
    ys = [point[1] for point in projected_bounds]
    x_margin = (max(xs) - min(xs)) * 0.04
    y_margin = (max(ys) - min(ys)) * 0.04
    ax.set_xlim(min(xs) - x_margin, max(xs) + x_margin)
    ax.set_ylim(min(ys) - y_margin, max(ys) + y_margin)

    cx.add_basemap(
        ax,
        crs="EPSG:3857",
        source=cx.providers.CartoDB.Positron,
        attribution_size=6,
        zorder=1,
    )

    ax.legend(handles=_legend_handles(), loc="lower right", framealpha=0.95, fontsize=10)
    ax.set_title("Zurich streets by dominant sound category")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the final Contextily sound map.")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS), help="Result CSV produced by submission_script.py.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_PLOTS_DIR / "dominant_sound_map_basemap.png"),
        help="Output image path.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    results_path = _resolve_path(args.results)
    output_path = _resolve_path(args.output)

    results = load_results_csv(results_path)
    plot_basemap(results, output_path)
    print(f"Saved basemap plot to {_display_path(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
