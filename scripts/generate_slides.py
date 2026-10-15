"""Inject fetched PostHog KPIs into templates/slide_contrats.html.

Reads data/posthog_data.json (produced by fetch_posthog_data.py), renders
the cumulative-domains chart as inline SVG from the real series, and
writes the final HTML to output/slide_contrats.html for capture_slides.py
to screenshot.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "posthog_data.json"
TEMPLATE_PATH = REPO_ROOT / "templates" / "slide_contrats.html"
OUTPUT_PATH = REPO_ROOT / "output" / "slide_contrats.html"

# Chart geometry - must match the static design validated in the template.
VIEWBOX_W = 820
VIEWBOX_H = 400
PLOT_LEFT = 56
PLOT_RIGHT = 810
PLOT_TOP = 10
PLOT_BOTTOM = 330
X_LABEL_Y = 356
Y_LABEL_X = 48
AXIS_COLOR = "#D9D9D9"
GRID_COLOR = "#F0E3DF"
LABEL_COLOR = "#8A8A8A"
LINE_COLOR = "#E8634A"

MONTHS_SHORT = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]


def format_int_fr(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_date_short(iso_date: str) -> str:
    _, month, day = iso_date.split("-")
    return f"{int(day)} {MONTHS_SHORT[int(month) - 1]}"


def format_date_ddmmyyyy(iso_date: str) -> str:
    year, month, day = iso_date.split("-")
    return f"{day}/{month}/{year}"


def nice_y_max(value: int) -> int:
    if value <= 0:
        return 100
    return (value // 100 + 1) * 100


def map_x(index: int, count: int) -> float:
    if count <= 1:
        return float(PLOT_LEFT)
    return PLOT_LEFT + (index / (count - 1)) * (PLOT_RIGHT - PLOT_LEFT)


def map_y(value: float, y_max: int) -> float:
    return PLOT_BOTTOM - (value / y_max) * (PLOT_BOTTOM - PLOT_TOP)


def curve_commands(points: list[tuple[float, float]]) -> str:
    """Quadratic-through-midpoints smoothing: smooth without overshoot risk."""
    parts = []
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        parts.append(f"Q{x0:.1f},{y0:.1f} {mx:.1f},{my:.1f}")
    parts.append(f"L{points[-1][0]:.1f},{points[-1][1]:.1f}")
    return " ".join(parts)


def build_cumulative_svg(days: list[str], data: list[int]) -> str:
    if not days or not data:
        logger.warning("Empty cumulative series, rendering an empty chart frame")
        data = [0]
        days = days or ["2026-09-08"]

    y_max = nice_y_max(max(data))
    points = [(map_x(i, len(data)), map_y(v, y_max)) for i, v in enumerate(data)]

    gridlines = []
    y_labels = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = PLOT_BOTTOM - frac * (PLOT_BOTTOM - PLOT_TOP)
        gridlines.append(f'<line x1="{PLOT_LEFT}" y1="{y:.1f}" x2="{PLOT_RIGHT}" y2="{y:.1f}" stroke="{GRID_COLOR}" stroke-width="1"/>')
        y_labels.append(
            f'<text x="{Y_LABEL_X}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-family="Inter, sans-serif" font-size="15" fill="{LABEL_COLOR}">{format_int_fr(round(frac * y_max))}</text>'
        )

    num_ticks = min(6, len(days))
    if num_ticks <= 1:
        tick_indices = [0]
    else:
        tick_indices = sorted({round(i * (len(days) - 1) / (num_ticks - 1)) for i in range(num_ticks)})

    x_labels = []
    for idx in tick_indices:
        x = map_x(idx, len(days))
        if idx == tick_indices[0]:
            anchor = "start"
        elif idx == tick_indices[-1]:
            anchor = "end"
        else:
            anchor = "middle"
        x_labels.append(
            f'<text x="{x:.1f}" y="{X_LABEL_Y}" text-anchor="{anchor}" '
            f'font-family="Inter, sans-serif" font-size="15" fill="{LABEL_COLOR}">{format_date_short(days[idx])}</text>'
        )

    line_d = f"M{points[0][0]:.1f},{points[0][1]:.1f} {curve_commands(points)}"
    area_d = (
        f"M{points[0][0]:.1f},{PLOT_BOTTOM} L{points[0][0]:.1f},{points[0][1]:.1f} "
        f"{curve_commands(points)} L{points[-1][0]:.1f},{PLOT_BOTTOM} Z"
    )
    last_x, last_y = points[-1]

    return f"""<svg viewBox="0 0 {VIEWBOX_W} {VIEWBOX_H}" width="100%" height="390" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="aire" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{LINE_COLOR}" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="{LINE_COLOR}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  {"".join(gridlines)}
  <line x1="{PLOT_LEFT}" y1="{PLOT_TOP}" x2="{PLOT_LEFT}" y2="{PLOT_BOTTOM}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>
  {"".join(y_labels)}
  <path d="{area_d}" fill="url(#aire)"/>
  <path d="{line_d}" fill="none" stroke="{LINE_COLOR}" stroke-width="6" stroke-linecap="round"/>
  <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="9" fill="#FFFFFF" stroke="{LINE_COLOR}" stroke-width="5"/>
  <line x1="{PLOT_LEFT}" y1="{PLOT_BOTTOM}" x2="{PLOT_RIGHT}" y2="{PLOT_BOTTOM}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>
  {"".join(x_labels)}
</svg>"""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not DATA_PATH.exists():
        logger.error("%s not found - run fetch_posthog_data.py first", DATA_PATH)
        return 1

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    cumulative_domains = data.get("cumulative_domains", {"days": [], "data": []})
    days = cumulative_domains.get("days", [])

    replacements = {
        "{{TOTAL_DOMAINS}}": format_int_fr(data["total_domains"]),
        "{{TOTAL_DOCS}}": format_int_fr(data["total_docs"]),
        "{{TOTAL_USERS}}": format_int_fr(data["total_users"]),
        "{{DERNIERE_MAJ}}": format_date_ddmmyyyy(days[-1]) if days else "N/A",
        "{{CUMULATIVE_DOMAINS_SVG}}": build_cumulative_svg(days, cumulative_domains.get("data", [])),
    }

    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(template, encoding="utf-8")
    logger.info("Wrote %s", OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
