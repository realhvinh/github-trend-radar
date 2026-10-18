# GitHub Trend Radar

A free, zero-server, **weekly top-10 GitHub repo star-growth tracker** with a mobile-friendly dashboard and archived Markdown, CSV, and JSON reports.

**Source of star growth:** GitHub REST API version `2026-03-10`, `GET /repos/{owner}/{repo}/stargazers/history`, which reports new stars per calendar week. **Source of candidate repos:** GitHub Trending (`?since=weekly`), global + selected languages. The tool ranks its *discovered candidate set* — this is not an exhaustive world-wide ranking of every repo on GitHub.

## Quick start — GitHub Actions (no computer/server needed)

1. Create a **public** GitHub repository (e.g. `github-trend-radar`). Upload **all contents** of this extracted folder, **including `.github/workflows/weekly.yml`**.
2. Go to **Actions → GitHub Trend Radar — Weekly Report → Run workflow** to fetch the first live report. The built-in `GITHUB_TOKEN` is automatically provided; there is no need to create your own PAT.
3. In **Settings → Pages**, choose **Deploy from a branch**, branch `main` (or your default branch), folder `/docs`. Save. Visit `https://YOUR_USERNAME.github.io/YOUR_REPO/`.
4. Scheduled collection happens every **Monday at 08:00 Vietnam time** (`01:00 UTC`) on GitHub Actions. GitHub may delay scheduled jobs. The source report and archive are committed by the workflow.

If your repo has workflow permissions disabled, allow **Read and write permissions** in **Settings → Actions → General → Workflow permissions** (repository/organization policy may affect this).

**Note:** GitHub may automatically disable scheduled workflows in public repos after 60 days of inactivity; re-enable the workflow if that happens. Automatically committed weekly updates ordinarily keep the repo active, but check the Actions tab if updates stop.

## Run on your machine

Requires Python 3.10+:

```bash
python -m pip install -r requirements.txt
# Optional but recommended for API rate limit, especially local runs:
export GITHUB_TOKEN=ghp_your_token_here
python -m src.radar
```

On Windows PowerShell:

```powershell
$env:GITHUB_TOKEN = "your_token_here"
python -m src.radar
```

Run without the internet just to preview the design:

```bash
python -m src.radar --demo
```

Open `demo/preview.html` in your browser. **Demo data is fictional and visibly labeled.**

Run tests:

```bash
python -m unittest discover -s tests -v
```

## What gets generated

- `docs/index.html` — standalone responsive dashboard, filterable by language/category and navigable by week; works without any JavaScript build step.
- `data/weeks/YYYY-MM-DD.json` — full data for each recorded week (the filename denotes the starting Sunday of a completed calendar week).
- `data/index.json` — at most 104 weekly reports for dashboard use.
- `reports/latest.md` — latest report readable directly on GitHub.
- `reports/YYYY-MM-DD.md` and `reports/YYYY-MM-DD.csv` — shareable per-week snapshots.

## Method and edge cases

1. Discover up to `max_candidates` repos from GitHub Trending worldwide and each chosen language. Deduplicate by `owner/repo`. If GitHub Trending returns fewer than 10, fallback discovery uses GitHub Search for recently created popular repositories.
2. Request each candidate's weekly star history via official GitHub REST API (`X-GitHub-Api-Version: 2026-03-10`).
3. Select the **last completed Sunday–Saturday week**, rather than the current partial week. GitHub cautions that API boundaries need not align perfectly with UTC; a 24-hour tolerance is used to match week records.
4. Rank by weekly new stars, descending. Enrich only the top 10 with descriptions, topics, total stars, etc. Label categories using basic keyword rules; they may be imperfect.
5. **Fallback if star history is unavailable for all candidates:** rank by the `stars this week` value parsed from GitHub Trending. The dashboard clearly labels this as a **rolling-week** measure, which should not be mixed with completed-calendar-week results.
6. If some history API responses fail and others succeed, use only valid calendar-week measurements. This prevents incompatible time windows being compared silently.
7. Archive the report, keeping up to two years in the embedded dashboard index and each per-week JSON file indefinitely.

**Limits:** (a) discovery is not a global exhaustive search; (b) GitHub may change its Trending HTML, so that parser may need maintenance; (c) recently deleted/unstarred events mean new-star activity differs from net growth in total stars; (d) high star growth does not guarantee code quality, security, or adoption; (e) when manually rerun in the same week, the report replaces that week's previous snapshot; and (f) the fallback report is a rolling seven days but saved under the same canonical week identifier, so it is tagged distinctly in `basis`.

Customize `config.json` for languages, candidate cap, number of winners and minimum stars.

## Useful links

- GitHub star-history endpoint: https://docs.github.com/en/rest/activity/starring?apiVersion=2026-03-10#get-repository-star-history
- GitHub Trending: https://github.com/trending?since=weekly
- GitHub Actions scheduled runs: https://docs.github.com/en/actions/reference/events-that-trigger-workflows#schedule

Released as a reference starter project; edit and publish in your own GitHub account.
