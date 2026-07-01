# posthog-tv-public

Hourly snapshots of PostHog dashboards, served via GitHub Pages for
digital signage on Samsung VXT screens.

## URLs

| Dashboard | PNG (1920×1080) |
|-----------|-----------------|
| 1 | https://user98765432123456789.github.io/posthog-tv-public/dashboard1.png |
| 2 | https://user98765432123456789.github.io/posthog-tv-public/dashboard2.png |
| 3 | https://user98765432123456789.github.io/posthog-tv-public/dashboard3.png |
| 4 | https://user98765432123456789.github.io/posthog-tv-public/dashboard4.png |
| 5 | https://user98765432123456789.github.io/posthog-tv-public/dashboard5.png |
| 6 | https://user98765432123456789.github.io/posthog-tv-public/dashboard6.png |
| 7 | https://user98765432123456789.github.io/posthog-tv-public/dashboard7.png |
| 8 | https://user98765432123456789.github.io/posthog-tv-public/dashboard8.png |

## How it works

A GitHub Actions workflow runs every hour:

1. Launches headless Chromium via Playwright.
2. Navigates to each configured PostHog dashboard share URL.
3. Waits for charts to render.
4. Captures `dashboard1.png` … `dashboard8.png` at 1920×1080.
5. Commits and pushes the new artifacts if they differ.

If any step fails, the workflow fails and the previous artifacts remain
untouched — the display keeps showing the last valid snapshot.

## Setup

### 1. Configure PostHog sharing

On `eu.posthog.com`, open each dashboard, click **Share**, enable
**Public access**, and copy the generated URL
(`https://eu.posthog.com/shared/<token>`).

### 2. Add the GitHub Secrets

In repository settings → Secrets and variables → Actions, create up to 8
repository secrets:

| Secret | Value |
|--------|-------|
| `POSTHOG_DASHBOARD_URL_1` | share URL for dashboard 1 |
| `POSTHOG_DASHBOARD_URL_2` | share URL for dashboard 2 |
| … | … |
| `POSTHOG_DASHBOARD_URL_8` | share URL for dashboard 8 |

Secrets that are left empty are silently skipped. At least one must be set.

### 3. Enable GitHub Pages

In repository settings → Pages, set Source to `main` branch, root folder.

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate   # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env     # then edit .env with your share URLs
python scripts/capture_dashboard.py
```

The script writes `dashboard1.png` … `dashboard8.png` to the repo root.

## Configuration

All configuration is via environment variables (see `.env.example`):

- `POSTHOG_DASHBOARD_URL_1` … `POSTHOG_DASHBOARD_URL_8` — public share URLs (at least one required)
- `RENDER_WAIT_MS` (optional, default 45000) — delay in ms after page load before screenshot

## Manual run

From the GitHub Actions tab, select **Update dashboard** workflow and
click **Run workflow**.
