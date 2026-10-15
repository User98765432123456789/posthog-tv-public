"""Capture a generated slide as a PNG using headless Chromium.

Usage: capture_slides.py [html_path] [png_path]
Defaults to output/slide_contrats.html -> slide_contrats.png (repo root)
when no arguments are given. Same approach as capture_dashboard.py, but
against a local file instead of a PostHog share URL.
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
DEFAULT_HTML_PATH = REPO_ROOT / "output" / "slide_contrats.html"
DEFAULT_PNG_PATH = REPO_ROOT / "slide_contrats.png"


def capture(html_path: Path, png_path: Path) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                device_scale_factor=1,
            )
            page = context.new_page()

            logger.info("Opening %s", html_path)
            page.goto(html_path.as_uri(), wait_until="networkidle")

            logger.info("Waiting for Google Fonts to finish loading")
            try:
                page.wait_for_function("document.fonts.status === 'loaded'", timeout=FONTS_TIMEOUT_MS)
            except PlaywrightTimeout:
                logger.warning("Timed out waiting for fonts to load, proceeding anyway")

            page.wait_for_timeout(500)

            logger.info("Capturing PNG -> %s", png_path)
            page.screenshot(path=str(png_path), full_page=False)
        finally:
            browser.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    html_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_HTML_PATH
    png_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DEFAULT_PNG_PATH

    if not html_path.exists():
        logger.error("%s not found - generate the slide HTML first", html_path)
        return 1

    try:
        capture(html_path, png_path)
    except Exception:
        logger.exception("Capture failed")
        return 1

    logger.info("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
