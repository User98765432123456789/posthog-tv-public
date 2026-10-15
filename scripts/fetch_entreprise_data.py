"""Fetch mySilae Entreprise KPIs from the PostHog API.

Each of the 3 source dashboards has exactly one insight (unlike the
mySilae Contrats dashboard), so tiles are read positionally - no name
matching needed. Writes a flat JSON ready for generate_entreprise_slide.py
to inject into templates/slide_entreprise.html.

Requires POSTHOG_API_KEY (personal API key with read access on project 15566).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

POSTHOG_HOST = "https://eu.posthog.com"
PROJECT_ID = 15566
REQUEST_TIMEOUT = 30

DASHBOARD_TOTAL_USERS = 760832
DASHBOARD_CUMULATIVE_USERS = 755511
DASHBOARD_BREAKDOWN_USER_TYPE = 737242

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "posthog_entreprise_data.json"


def api_get(session: requests.Session, path: str, params: dict | None = None) -> dict:
    url = f"{POSTHOG_HOST}{path}"
    resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if not resp.ok:
        logger.error("PostHog API error %s on %s: %s", resp.status_code, url, resp.text[:2000])
    resp.raise_for_status()
    return resp.json()


def fetch_single_insight_result(session: requests.Session, dashboard_id: int) -> list:
    """Each dashboard has exactly one insight - take it positionally."""
    dashboard = api_get(session, f"/api/projects/{PROJECT_ID}/dashboards/{dashboard_id}/")
    tiles = dashboard.get("tiles", [])
    if not tiles or not tiles[0].get("insight"):
        logger.error("Dashboard %s has no insight tile", dashboard_id)
        return []

    insight = tiles[0]["insight"]
    logger.info("Dashboard %s -> insight %r (id=%s)", dashboard_id, insight.get("name"), insight.get("id"))

    data = api_get(
        session,
        f"/api/projects/{PROJECT_ID}/insights/{insight['id']}/",
        params={"refresh": "true"},
    )
    return data.get("result") or []


def extract_counter(result: list) -> int:
    if not result:
        return 0
    series = result[0]
    if "aggregated_value" in series and series["aggregated_value"] is not None:
        return round(series["aggregated_value"])
    data = series.get("data") or []
    if data:
        return round(data[-1])
    return round(series.get("count", 0))


def extract_series(result: list) -> dict[str, list]:
    if not result:
        return {"days": [], "data": []}
    series = result[0]
    days = series.get("days") or series.get("labels") or []
    data = series.get("data") or []
    return {"days": days, "data": [round(v) for v in data]}


# PostHog's raw breakdown property values -> display label. Anything not
# listed here falls back to a capitalized version of the raw value.
LABEL_DISPLAY_MAP = {
    "admin": "Admin",
    "manager": "Manager",
    "employee": "Employé",
}


def extract_breakdown(result: list) -> list[dict]:
    """Returns [{"label": ..., "value": ...}, ...]. breakdown_value can come
    back as a single-element list (e.g. ["employee"]) rather than a plain
    string, depending on how the insight is configured."""
    rows = []
    for series in result:
        raw = series.get("breakdown_value") or series.get("label") or "unknown"
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else "unknown"
        raw = str(raw).strip().lower()
        label = LABEL_DISPLAY_MAP.get(raw, raw.capitalize())

        data = series.get("data") or []
        value = series.get("aggregated_value")
        if value is None:
            value = data[-1] if data else series.get("count", 0)
        rows.append({"label": label, "value": round(value)})
    logger.info("Breakdown rows: %s", rows)
    return rows


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    api_key = os.environ.get("POSTHOG_API_KEY")
    if not api_key:
        logger.error("POSTHOG_API_KEY is not set")
        return 1

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"

    total_users_result = fetch_single_insight_result(session, DASHBOARD_TOTAL_USERS)
    cumulative_result = fetch_single_insight_result(session, DASHBOARD_CUMULATIVE_USERS)
    breakdown_result = fetch_single_insight_result(session, DASHBOARD_BREAKDOWN_USER_TYPE)

    cumulative_users = extract_series(cumulative_result)
    days = cumulative_users["days"]

    output = {
        "total_users": extract_counter(total_users_result),
        "cumulative_users": cumulative_users,
        "breakdown": extract_breakdown(breakdown_result),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote %s", OUTPUT_PATH)
    logger.info("KPIs: %s users inscrits, %d jours de cumul, %d catégories de breakdown",
                output["total_users"], len(days), len(output["breakdown"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
