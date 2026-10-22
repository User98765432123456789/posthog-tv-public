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

# Chart geometry - must match the light-theme design validated in the template.
VIEWBOX_W = 820
VIEWBOX_H = 400
PLOT_LEFT = 56
PLOT_RIGHT = 810
PLOT_TOP = 34
PLOT_BOTTOM = 330
X_LABEL_Y = 356
Y_LABEL_X = 48
AXIS_COLOR = "#D9D9D9"
GRID_COLOR = "#F0E3DF"
LABEL_COLOR = "#8A8A8A"
LINE_COLOR = "#E8634A"
PAST_BAR_COLOR = "#F7D8CE"
VALUE_LABEL_COLOR = "#C94E36"

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


def format_date_ddmmyyyy(iso_date: str) -> str:
    year, month, day = iso_date.split("-")
    return f"{day}/{month}/{year}"


MONTHS_LONG = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def format_month_year(iso_date: str) -> str:
    year, month, _ = iso_date.split("-")
    return f"{MONTHS_LONG[int(month) - 1]} {year}"


GRID_STEP = 500_000


def nice_y_max(value: int) -> int:
    """Smallest multiple of GRID_STEP that is >= value, so the axis always
    has headroom above the real data without needing a hand-picked cap."""
    if value <= 0:
        return GRID_STEP
    return math.ceil(value / GRID_STEP) * GRID_STEP


def map_y(value: float, y_max: int) -> float:
    return PLOT_BOTTOM - (value / y_max) * (PLOT_BOTTOM - PLOT_TOP)


def aggregate_by_quarter(days: list[str], data: list[int]) -> list[tuple[str, int]]:
    """Collapses monthly cumulative points into one value per quarter - the
    last (most recent) month seen in that quarter, since days are ascending."""
    buckets: dict[tuple[int, int], int] = {}
    for day, value in zip(days, data):
        year, month, _ = day.split("-")
        quarter = (int(month) - 1) // 3 + 1
        buckets[(int(year), quarter)] = value
    ordered_keys = sorted(buckets.keys())
    return [(f"Q{quarter} {year % 100:02d}", buckets[(year, quarter)]) for year, quarter in ordered_keys]


def format_bar_label(value: float) -> str:
    """Truncates rather than rounds, so e.g. 3.056M reads "3,0 M" - never
    implies a milestone (3,1 M) has been reached before it actually has."""
    if value >= 1_000_000:
        tenths = int(value) // 100_000
        return f"{tenths / 10:.1f}".replace(".", ",") + " M"
    if value >= 1_000:
        tenths = int(value) // 100
        return f"{tenths / 10:.1f}".replace(".", ",") + " k"
    return str(round(value))


def build_quarterly_bar_svg(days: list[str], data: list[int], total_users: int | None = None) -> str:
    if not days or not data:
        logger.warning("Empty cumulative series, rendering an empty chart frame")
        return f'<svg viewBox="0 0 {VIEWBOX_W} {VIEWBOX_H}" width="100%" height="390" xmlns="http://www.w3.org/2000/svg"></svg>'

    quarters = aggregate_by_quarter(days, data)
    if total_users is not None:
        # Keep the last bar's value and label in lockstep with the big KPI
        # counter - the quarterly bucket's own last data point can be a few
        # thousand users stale relative to the authoritative total.
        quarters[-1] = (quarters[-1][0], total_users)
    y_max = nice_y_max(max(value for _, value in quarters))
    n = len(quarters)

    gridlines = []
    y_labels = []
    num_steps = round(y_max / GRID_STEP)
    for i in range(num_steps + 1):
        value_at_step = i * GRID_STEP
        y = PLOT_BOTTOM - (value_at_step / y_max) * (PLOT_BOTTOM - PLOT_TOP)
        gridlines.append(f'<line x1="{PLOT_LEFT}" y1="{y:.1f}" x2="{PLOT_RIGHT}" y2="{y:.1f}" stroke="{GRID_COLOR}" stroke-width="1"/>')
        y_labels.append(
            f'<text x="{Y_LABEL_X}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-family="Inter, sans-serif" font-size="15" fill="{LABEL_COLOR}">{format_compact_fr(value_at_step)}</text>'
        )

    slot_width = (PLOT_RIGHT - PLOT_LEFT) / n
    bar_width = slot_width * 0.5

    bars = []
    x_labels = []
    value_labels = []
    for i, (label, value) in enumerate(quarters):
        center_x = PLOT_LEFT + slot_width * (i + 0.5)
        raw_top_y = map_y(value, y_max)
        # Clip the bar at the plot's top edge when a value exceeds the fixed
        # y-axis cap, instead of letting it overflow into the label's space.
        top_y = max(raw_top_y, PLOT_TOP)
        is_capped = raw_top_y < PLOT_TOP
        height = PLOT_BOTTOM - top_y
        is_edge = i == 0 or i == n - 1
        bar_fill = LINE_COLOR if i == n - 1 else PAST_BAR_COLOR
        bars.append(
            f'<rect x="{center_x - bar_width / 2:.1f}" y="{top_y:.1f}" width="{bar_width:.1f}" '
            f'height="{height:.1f}" rx="6" fill="{bar_fill}"/>'
        )
        x_labels.append(
            f'<text x="{center_x:.1f}" y="{X_LABEL_Y}" text-anchor="middle" '
            f'font-family="Inter, sans-serif" font-size="13" fill="{LABEL_COLOR}">{label}</text>'
        )
        if is_edge:
            label_y = (PLOT_TOP - 14) if is_capped else max(top_y - 12, PLOT_TOP - 14)
            value_labels.append(
                f'<text x="{center_x:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                f'font-family="Montserrat, sans-serif" font-size="17" font-weight="700" fill="{VALUE_LABEL_COLOR}">{format_bar_label(value)}</text>'
            )

    return f"""<svg viewBox="0 0 {VIEWBOX_W} {VIEWBOX_H}" width="100%" height="390" xmlns="http://www.w3.org/2000/svg">
  {"".join(gridlines)}
  <line x1="{PLOT_LEFT}" y1="{PLOT_TOP}" x2="{PLOT_LEFT}" y2="{PLOT_BOTTOM}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>
  {"".join(y_labels)}
  {"".join(bars)}
  <line x1="{PLOT_LEFT}" y1="{PLOT_BOTTOM}" x2="{PLOT_RIGHT}" y2="{PLOT_BOTTOM}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>
  {"".join(x_labels)}
  {"".join(value_labels)}
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
        "{{DERNIERE_MAJ}}": format_date_ddmmyyyy(data["fetched_at"][:10]) if data.get("fetched_at") else "N/A",
        "{{CUMULATIVE_USERS_SVG}}": build_quarterly_bar_svg(days, cumulative_users.get("data", []), data.get("total_users")),
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
