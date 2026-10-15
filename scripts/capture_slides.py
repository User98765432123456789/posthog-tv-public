"""Capture the generated mySilae Contrats slide as a PNG using headless Chromium.

Reads output/slide_contrats.html (produced by generate_slides.py) and
writes slide_contrats.png at the repo root, at 1920x1080 - same approach
as capture_dashboard.py, but against a local file instead of a PostHog
share URL.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080
FONTS_TIMEOUT_MS = 15000

REPO_ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = REPO_ROOT / "output" / "slide_contrats.html"
PNG_PATH = REPO_ROOT / "slide_contrats.png"


def capture() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                device_scale_factor=1,
            )
            page = context.new_page()

            logger.info("Opening %s", HTML_PATH)
            page.goto(HTML_PATH.as_uri(), wait_until="networkidle")

            logger.info("Waiting for Google Fonts to finish loading")
            try:
                page.wait_for_function("document.fonts.status === 'loaded'", timeout=FONTS_TIMEOUT_MS)
            except PlaywrightTimeout:
                logger.warning("Timed out waiting for fonts to load, proceeding anyway")

            page.wait_for_timeout(500)

            logger.info("Capturing PNG -> %s", PNG_PATH)
            page.screenshot(path=str(PNG_PATH), full_page=False)
        finally:
            browser.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not HTML_PATH.exists():
        logger.error("%s not found - run generate_slides.py first", HTML_PATH)
        return 1

    try:
        capture()
    except Exception:
        logger.exception("Capture failed")
        return 1

    logger.info("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
