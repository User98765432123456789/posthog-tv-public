"""Fetch mySilae Contrats KPIs from the PostHog API.

Reads the dashboard identified by DASHBOARD_ID, matches its tiles by insight
name, pulls fresh results for each, and writes a flat JSON ready for
generate_slides.py to inject into templates/slide_contrats.html.

Requires POSTHOG_API_KEY (personal API key with read access on the project).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

POSTHOG_HOST = "https://eu.posthog.com"
PROJECT_ID = 17613
DASHBOARD_ID = 938631
REQUEST_TIMEOUT = 30

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "posthog_data.json"

# Distinctive substring (lowercase) found in the tile name -> role used below.
# Tile names carry a variable prefix ("mySilae Contrats – " / "mySilae Contrats - ")
# so we match on the distinctive tail instead of the full name.
NAME_KEYWORD_TO_ROLE = {
    "total activated domains": "total_domains",
    "total documents generated": "total_docs",
    "total active users": "total_users",
    "cumulative activated domains": "cumulative_domains",
    "cumulative documents generated": "cumulative_docs",
}

FR_MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def api_get(session: requests.Session, path: str, params: dict | None = None) -> dict:
    url = f"{POSTHOG_HOST}{path}"
    resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_dashboard_tiles(session: requests.Session) -> list[dict]:
    data = api_get(session, f"/api/projects/{PROJECT_ID}/dashboards/{DASHBOARD_ID}/")
    tiles = data.get("tiles", [])
    logger.info("Dashboard has %d tiles", len(tiles))
    return tiles


def fetch_insight_result(session: requests.Session, insight_id: int) -> list:
    """Force a fresh computation so the TV slide never shows stale numbers."""
    data = api_get(
        session,
        f"/api/projects/{PROJECT_ID}/insights/{insight_id}/",
        params={"refresh": "true"},
    )
    return data.get("result") or []


def extract_counter(result: list) -> int:
    """Best-effort extraction of a single aggregated number from a trend result."""
    if not result:
        return 0
    series = result[0]
    if "aggregated_value" in series and series["aggregated_value"] is not None:
        return round(series["aggregated_value"])
    data = series.get("data") or []
    if data:
        return round(data[-1])
    return round(series.get("count", 0))


def extract_breakdown_counters(result: list) -> dict[str, int]:
    """For a trend insight broken down by a property (e.g. user role)."""
    counters: dict[str, int] = {}
    for series in result:
        label = str(series.get("breakdown_value") or series.get("label") or "unknown")
        data = series.get("data") or []
        value = series.get("aggregated_value")
        if value is None:
            value = data[-1] if data else series.get("count", 0)
        counters[label.strip().lower()] = round(value)
    return counters


def extract_series(result: list) -> dict[str, list]:
    """For a cumulative line chart: paired date labels + cumulative values."""
    if not result:
        return {"days": [], "data": []}
    series = result[0]
    days = series.get("days") or series.get("labels") or []
    data = series.get("data") or []
    return {"days": days, "data": [round(v) for v in data]}


def pick_user_count(counters: dict[str, int], *needles: str) -> int:
    for label, value in counters.items():
        if any(needle in label for needle in needles):
            return value
    return 0


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    api_key = os.environ.get("POSTHOG_API_KEY")
    if not api_key:
        logger.error("POSTHOG_API_KEY is not set")
        return 1

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"

    tiles = fetch_dashboard_tiles(session)

    insights_by_role: dict[str, dict] = {}
    for tile in tiles:
        insight = tile.get("insight")
        if not insight:
            continue
        name = (insight.get("name") or "").strip().lower()
        role = next((r for kw, r in NAME_KEYWORD_TO_ROLE.items() if kw in name), None)
        if not role:
            logger.info("Skipping unmapped tile: %r (id=%s)", insight.get("name"), insight.get("id"))
            continue
        insights_by_role[role] = insight
        logger.info("Matched tile %r -> role %s (insight id=%s)", insight.get("name"), role, insight.get("id"))

    missing = sorted(set(NAME_KEYWORD_TO_ROLE.values()) - set(insights_by_role))
    if missing:
        logger.error("Could not find dashboard tiles for roles: %s", missing)
        return 1

    results: dict[str, list] = {}
    for role, insight in insights_by_role.items():
        results[role] = fetch_insight_result(session, insight["id"])

    users_breakdown = extract_breakdown_counters(results["total_users"])

    now = __import__("datetime").datetime.utcnow()
    date_maj = f"{now.day} {FR_MONTHS[now.month - 1]} {now.year}"

    output = {
        "total_domains": extract_counter(results["total_domains"]),
        "total_docs": extract_counter(results["total_docs"]),
        "total_users": sum(users_breakdown.values()),
        "users_client": pick_user_count(users_breakdown, "client"),
        "users_collab": pick_user_count(users_breakdown, "collab"),
        "cumulative_domains": extract_series(results["cumulative_domains"]),
        "cumulative_docs": extract_series(results["cumulative_docs"]),
        "date_maj": date_maj,
        "fetched_at": now.isoformat() + "Z",
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote %s", OUTPUT_PATH)
    logger.info("KPIs: %s domaines, %s docs, %s users (%s client / %s collab)",
                output["total_domains"], output["total_docs"], output["total_users"],
                output["users_client"], output["users_collab"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
