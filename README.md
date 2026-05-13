# posthog-tv-public

Hourly snapshots of a PostHog dashboard, served via GitHub Pages for
digital signage on Samsung VXT screens.

## URLs

- PNG (1920x1080): https://user98765432123456789.github.io/posthog-tv-public/dashboard.png
- PDF (1920x1080): https://user98765432123456789.github.io/posthog-tv-public/dashboard.pdf

## How it works

A GitHub Actions workflow runs every hour:

1. Launches headless Chromium via Playwright.
2. Navigates to the public PostHog dashboard share URL.
3. Waits for charts to render.
4. Captures `dashboard.png` and `dashboard.pdf` at 1920x1080.
5. Commits and pushes the new artifacts if they differ.

If any step fails, the workflow fails and the previous artifacts remain
untouched - the display keeps showing the last valid snapshot.

## Setup

### 1. Configure PostHog sharing

On `eu.posthog.com`, open the dashboard, click **Share**, enable
**Public access**, and copy the generated URL
(`https://eu.posthog.com/shared/<token>`).

### 2. Add the GitHub Secret

In repository settings -> Secrets and variables -> Actions, create a new
repository secret:

- Name: `POSTHOG_DASHBOARD_URL`
- Value: the share URL from step 1

### 3. Enable GitHub Pages

In repository settings -> Pages, set Source to `main` branch, root folder.

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate   # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env     # then edit .env with your share URL
python scripts/capture_dashboard.py
```

The script writes `dashboard.png` and `dashboard.pdf` to the repo root.

## Configuration

All configuration is via environment variables (see `.env.example`):

- `POSTHOG_DASHBOARD_URL` (required) - public share URL of the dashboard
- `RENDER_WAIT_MS` (optional, default 15000) - delay in ms after page
  load before screenshot, to let charts finish rendering

## Manual run

From the GitHub Actions tab, select **Update dashboard** workflow and
click **Run workflow**.
