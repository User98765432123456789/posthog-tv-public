"""Capture a public PostHog dashboard as PNG and PDF using headless Chromium.

Reads POSTHOG_DASHBOARD_URL from environment (or .env locally).
Outputs dashboard.png and dashboard.pdf at the repo root.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080
DEFAULT_RENDER_WAIT_MS = 15000
NAVIGATION_TIMEOUT_MS = 60000

REPO_ROOT = Path(__file__).resolve().parent.parent
PNG_PATH = REPO_ROOT / "dashboard.png"
PDF_PATH = REPO_ROOT / "dashboard.pdf"


def capture(url: str, render_wait_ms: int) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.set_default_timeout(NAVIGATION_TIMEOUT_MS)

            logger.info("Navigating to dashboard URL")
            page.goto(url, wait_until="networkidle")

            logger.info("Waiting %d ms for charts to settle", render_wait_ms)
            page.wait_for_timeout(render_wait_ms)

            logger.info("Capturing PNG -> %s", PNG_PATH)
            page.screenshot(path=str(PNG_PATH), full_page=False)

            logger.info("Capturing PDF -> %s", PDF_PATH)
            page.pdf(
                path=str(PDF_PATH),
                width=f"{VIEWPORT_WIDTH}px",
                height=f"{VIEWPORT_HEIGHT}px",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
        finally:
            browser.close()


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    url = os.environ.get("POSTHOG_DASHBOARD_URL")
    if not url:
        logger.error("POSTHOG_DASHBOARD_URL is not set")
        return 1

    try:
        render_wait_ms = int(os.environ.get("RENDER_WAIT_MS", DEFAULT_RENDER_WAIT_MS))
    except ValueError:
        logger.error("RENDER_WAIT_MS must be an integer (ms)")
        return 1

    try:
        capture(url, render_wait_ms)
    except PlaywrightTimeout as exc:
        logger.error("Timeout while capturing dashboard: %s", exc)
        return 1
    except Exception as exc:
        logger.exception("Capture failed: %s", exc)
        return 1

    logger.info("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
