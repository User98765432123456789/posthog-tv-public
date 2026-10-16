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
| mySilae Contrats slide | https://user98765432123456789.github.io/posthog-tv-public/slide_contrats.png |
| mySilae Entreprise slide | https://user98765432123456789.github.io/posthog-tv-public/slide_entreprise.png |

## How it works

A GitHub Actions workflow runs every hour:

1. Launches headless Chromium via Playwright.
2. Navigates to each configured PostHog dashboard share URL.
3. Waits for charts to render.
4. Captures `dashboard1.png` … `dashboard8.png` at 1920×1080.
5. Commits and pushes the new artifacts if they differ.

If any step fails, the workflow fails and the previous artifacts remain
untouched — the display keeps showing the last valid snapshot.

A second workflow runs daily at 7:00 UTC (8:00 in winter, 9:00 in
summer CEST — GitHub Actions cron has no timezone support) to build the
corporate "mySilae Contrats" slide:

1. Fetches KPIs from the PostHog API (dashboard `938631`, project `17613`).
2. Injects them into `templates/slide_contrats.html` via `scripts/generate_slides.py`.
3. Screenshots the result with Playwright to `slide_contrats.png`.
4. Commits and pushes it if it differs.

A third workflow, on the same daily schedule, builds the "mySilae
Entreprise" slide (3M+ registered-users milestone, project `15566`,
dashboards `760832`/`755511`/`737242`):

1. Fetches KPIs from the PostHog API via `scripts/fetch_entreprise_data.py`.
2. Injects them into `templates/slide_entreprise.html` via `scripts/generate_entreprise_slide.py`.
3. Screenshots the result with Playwright to `slide_entreprise.png`.
4. Commits and pushes it if it differs.

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

### 4. Add the PostHog API key (for the mySilae Contrats and mySilae Entreprise slides)

Create a personal API key on `eu.posthog.com` (Settings → Personal API
keys) with read access to both projects (`17613` and `15566`), then add
it as a repository secret named `POSTHOG_API_KEY`.

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

For the mySilae Contrats slide:

```bash
cp .env.example .env     # then edit .env with POSTHOG_API_KEY
python scripts/fetch_posthog_data.py   # writes data/posthog_data.json
python scripts/generate_slides.py      # writes output/slide_contrats.html
python scripts/capture_slides.py       # writes slide_contrats.png
```

For the mySilae Entreprise slide:

```bash
python scripts/fetch_entreprise_data.py     # writes data/posthog_entreprise_data.json
python scripts/generate_entreprise_slide.py # writes output/slide_entreprise.html
python scripts/capture_slides.py output/slide_entreprise.html slide_entreprise.png
```

## Configuration

All configuration is via environment variables (see `.env.example`):

- `POSTHOG_DASHBOARD_URL_1` … `POSTHOG_DASHBOARD_URL_8` — public share URLs (at least one required)
- `RENDER_WAIT_MS` (optional, default 45000) — delay in ms after page load before screenshot

## Manual run

From the GitHub Actions tab, select the **Update dashboard**,
**Update slide_contrats**, or **Update slide_entreprise** workflow and
click **Run workflow**.
