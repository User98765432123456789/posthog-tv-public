"""Capture public PostHog dashboards as PNG using headless Chromium.

Reads POSTHOG_DASHBOARD_URL_1 … POSTHOG_DASHBOARD_URL_8 from environment.
Outputs dashboard1.png … dashboard8.png at the repo root.
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
DEFAULT_RENDER_WAIT_MS = 45000
NAVIGATION_TIMEOUT_MS = 60000

REPO_ROOT = Path(__file__).resolve().parent.parent


def capture(url: str, index: int, render_wait_ms: int) -> None:
    png_path = REPO_ROOT / f"dashboard{index}.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.set_default_timeout(NAVIGATION_TIMEOUT_MS)

            logger.info("[%d] Navigating to dashboard URL", index)
            page.goto(url, wait_until="domcontentloaded")

            logger.info("[%d] Waiting for PostHog app to mount", index)
            try:
                page.wait_for_selector(".InsightCard, .Dashboard", timeout=30000)
            except PlaywrightTimeout:
                logger.warning("[%d] Dashboard/InsightCard not found — page may have a different structure", index)

            logger.info("[%d] Waiting for insights to start loading", index)
            try:
                page.wait_for_function(
                    "document.querySelectorAll('.LemonSkeleton').length > 0",
                    timeout=15000,
                )
            except PlaywrightTimeout:
                logger.warning("[%d] No skeletons appeared — page may have loaded instantly", index)

            logger.info("[%d] Waiting for insights to finish loading (timeout %d ms)", index, render_wait_ms)
            try:
                page.wait_for_function(
                    "document.querySelectorAll('.LemonSkeleton').length === 0",
                    timeout=render_wait_ms,
                )
            except PlaywrightTimeout:
                logger.warning("[%d] Timed out waiting for skeletons to clear, proceeding anyway", index)

            logger.info("[%d] Waiting for 'Loading' indicators to disappear", index)
            try:
                page.wait_for_function(
                    """() => !Array.from(document.querySelectorAll('.LemonTag--warning, [class*="loading"]'))
                        .some(el => el.textContent.trim() === 'Loading')
                        && !Array.from(document.querySelectorAll('*'))
                        .some(el => el.childNodes.length === 1
                            && el.childNodes[0].nodeType === 3
                            && el.childNodes[0].textContent.trim() === 'Loading')""",
                    timeout=60000,
                )
            except PlaywrightTimeout:
                logger.warning("[%d] Timed out waiting for 'Loading' text to clear, proceeding anyway", index)

            page.wait_for_timeout(5000)

            logger.info("[%d] Capturing PNG -> %s", index, png_path)
            page.screenshot(path=str(png_path), full_page=False)
        finally:
            browser.close()


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        render_wait_ms = int(os.environ.get("RENDER_WAIT_MS", DEFAULT_RENDER_WAIT_MS))
    except ValueError:
        logger.error("RENDER_WAIT_MS must be an integer (ms)")
        return 1

    urls = {
        i: os.environ.get(f"POSTHOG_DASHBOARD_URL_{i}")
        for i in range(1, 9)
    }
    configured = {i: u for i, u in urls.items() if u}

    if not configured:
        logger.error("No POSTHOG_DASHBOARD_URL_1 … POSTHOG_DASHBOARD_URL_8 is set")
        return 1

    exit_code = 0
    for index, url in configured.items():
        try:
            capture(url, index, render_wait_ms)
        except PlaywrightTimeout as exc:
            logger.error("[%d] Timeout while capturing dashboard: %s", index, exc)
            exit_code = 1
        except Exception as exc:
            logger.exception("[%d] Capture failed: %s", index, exc)
            exit_code = 1

    logger.info("Done (%d/%d captured)", len(configured) - exit_code, len(configured))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
