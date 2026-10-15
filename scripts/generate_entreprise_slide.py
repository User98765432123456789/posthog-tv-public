"""Inject fetched mySilae Entreprise KPIs into templates/slide_entreprise.html.

Reads data/posthog_entreprise_data.json (produced by fetch_entreprise_data.py),
renders the cumulative-users chart and the user-type breakdown donut as
inline SVG from the real data, and writes the final HTML to
output/slide_entreprise.html for capture_slides.py to screenshot.
"""

from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "posthog_entreprise_data.json"
TEMPLATE_PATH = REPO_ROOT / "templates" / "slide_entreprise.html"
OUTPUT_PATH = REPO_ROOT / "output" / "slide_entreprise.html"

# Chart geometry - must match the dark-theme design validated in the template.
VIEWBOX_W = 820
VIEWBOX_H = 400
PLOT_LEFT = 56
PLOT_RIGHT = 810
PLOT_TOP = 10
PLOT_BOTTOM = 330
X_LABEL_Y = 356
Y_LABEL_X = 48
GRID_COLOR = "rgba(255,255,255,0.08)"
AXIS_COLOR = "rgba(255,255,255,0.3)"
LABEL_COLOR = "#B8ACA5"
LINE_COLOR = "#E8634A"

MONTHS_SHORT = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]
MONTHS_LONG = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

# Fixed display order and color per profile - darkest to lightest, regardless
# of which profile has the most users. Any unexpected category (not one of
# these three) is appended after, in a fallback color.
PROFILE_ORDER = ["Admin", "Manager", "Employé"]
PROFILE_COLORS = {"Admin": "#8B3A2B", "Manager": "#E8634A", "Employé": "#F2A68C"}
FALLBACK_COLORS = ["#FBD8C7", "#8A6B5E", "#D9A48C"]


def format_int_fr(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_compact_fr(value: float) -> str:
    value = round(value)
    if value >= 1_000_000:
        s = f"{value / 1_000_000:.1f}"
    elif value >= 1_000:
        s = f"{value / 1_000:.1f}"
    else:
        return str(value)
    if s.endswith(".0"):
        s = s[:-2]
    suffix = " M" if value >= 1_000_000 else " k"
    return s.replace(".", ",") + suffix


def format_date_short(iso_date: str) -> str:
    """"2024-02-15" -> "févr. 24" - the data spans years, so axis ticks need the year, not the day."""
    year, month, _ = iso_date.split("-")
    return f"{MONTHS_SHORT[int(month) - 1]} {year[2:]}"


def format_month_year(iso_date: str) -> str:
    year, month, _ = iso_date.split("-")
    return f"{MONTHS_LONG[int(month) - 1]} {year}"


def format_date_ddmmyyyy(iso_date: str) -> str:
    year, month, day = iso_date.split("-")
    return f"{day}/{month}/{year}"


def nice_y_max(value: int) -> int:
    if value <= 0:
        return 100
    for threshold, step in (
        (1_000, 100),
        (10_000, 1_000),
        (100_000, 10_000),
        (1_000_000, 100_000),
        (10_000_000, 500_000),
    ):
        if value < threshold:
            return (value // step + 1) * step
    return (value // 1_000_000 + 1) * 1_000_000


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
        days = days or ["2026-01-01"]

    y_max = nice_y_max(max(data))
    points = [(map_x(i, len(data)), map_y(v, y_max)) for i, v in enumerate(data)]

    gridlines = []
    y_labels = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = PLOT_BOTTOM - frac * (PLOT_BOTTOM - PLOT_TOP)
        gridlines.append(f'<line x1="{PLOT_LEFT}" y1="{y:.1f}" x2="{PLOT_RIGHT}" y2="{y:.1f}" stroke="{GRID_COLOR}" stroke-width="1"/>')
        y_labels.append(
            f'<text x="{Y_LABEL_X}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-family="Inter, sans-serif" font-size="15" fill="{LABEL_COLOR}">{format_compact_fr(frac * y_max)}</text>'
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


def order_breakdown(breakdown: list[dict]) -> list[dict]:
    """Admin, then Manager, then Employé - regardless of which has the most
    users. Any unexpected category is appended after, sorted by value."""
    by_label = {row["label"]: row["value"] for row in breakdown}
    ordered = []
    for label in PROFILE_ORDER:
        if label in by_label:
            ordered.append({"label": label, "value": by_label.pop(label)})
    for label, value in sorted(by_label.items(), key=lambda kv: kv[1], reverse=True):
        ordered.append({"label": label, "value": value})
    return ordered


def build_donut(breakdown: list[dict]) -> tuple[str, str]:
    """Returns (donut_svg, legend_rows_html)."""
    if not breakdown:
        logger.warning("Empty breakdown, rendering an empty donut")
        return (
            '<svg viewBox="0 0 200 200" width="180" height="180" xmlns="http://www.w3.org/2000/svg"></svg>',
            "",
        )

    breakdown = order_breakdown(breakdown)
    total = sum(row["value"] for row in breakdown) or 1
    r = 76
    circumference = 2 * math.pi * r

    circles = []
    legend_rows = []
    cumulative_fraction = 0.0
    fallback_index = 0
    for row in breakdown:
        fraction = row["value"] / total
        color = PROFILE_COLORS.get(row["label"])
        if color is None:
            color = FALLBACK_COLORS[fallback_index % len(FALLBACK_COLORS)]
            fallback_index += 1
        length = fraction * circumference
        offset = -(cumulative_fraction * circumference)
        circles.append(
            f'<circle cx="100" cy="100" r="{r}" fill="none" stroke="{color}" stroke-width="28" '
            f'stroke-dasharray="{length:.2f} {circumference - length:.2f}" stroke-dashoffset="{offset:.2f}"/>'
        )
        legend_rows.append(f"""              <div class="legende-ligne">
                <div class="legende-puce" style="background: {color};"></div>
                <div class="legende-label">{row['label']}</div>
                <div class="legende-valeur">{round(fraction * 100)}&nbsp;%</div>
              </div>""")
        cumulative_fraction += fraction

    donut_svg = f"""<svg viewBox="0 0 200 200" width="180" height="180" xmlns="http://www.w3.org/2000/svg">
              <g transform="rotate(-90 100 100)">
                {"".join(circles)}
              </g>
            </svg>"""

    return donut_svg, "\n".join(legend_rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not DATA_PATH.exists():
        logger.error("%s not found - run fetch_entreprise_data.py first", DATA_PATH)
        return 1

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    cumulative_users = data.get("cumulative_users", {"days": [], "data": []})
    days = cumulative_users.get("days", [])
    donut_svg, legend_rows = build_donut(data.get("breakdown", []))

    replacements = {
        "{{TOTAL_USERS}}": format_int_fr(data["total_users"]),
        "{{CUMUL_DEPUIS}}": format_month_year(days[0]) if days else "N/A",
        "{{DERNIERE_MAJ}}": format_date_ddmmyyyy(days[-1]) if days else "N/A",
        "{{CUMULATIVE_USERS_SVG}}": build_cumulative_svg(days, cumulative_users.get("data", [])),
        "{{DONUT_SVG}}": donut_svg,
        "{{LEGEND_ROWS}}": legend_rows,
    }

    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(template, encoding="utf-8")
    logger.info("Wrote %s", OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
