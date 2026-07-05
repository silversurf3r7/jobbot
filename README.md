# jobbot

Job helper for [hiring.cafe](https://hiring.cafe/): scrapes postings, keeps only
jobs hosted on **Ashby**, **Greenhouse**, or **Lever**, and gives you a web UI to
browse them, open applications, and track what you've done.

## Run the web UI

```sh
.venv/bin/python server.py
# open http://localhost:8765
```

- **Open ↗** opens the application in a new tab and marks the job `OPENED`.
- **✓ / ✗ / ↺** mark a job `SUBMITTED` / `SKIPPED` / reset to `NEW`.
- Chips at the top filter by status; there's also text search, a **Remote only**
  toggle (on by default, remembered across reloads), a source filter, and
  sorting by compensation or company.
- **Scrape** re-runs the hiring.cafe scraper in the background and reloads the
  list when done. Type keywords in the box next to it to scrape a custom
  hiring.cafe search (comma-separate for several, e.g. `react, vue`); leave it
  blank for the default DevOps-family queries. Results merge into the existing
  list (deduped by URL) and are tagged with the search that found them — use
  the **All searches** dropdown to filter by tag.
- The **age dropdown** next to Scrape limits how old listings can be, from the
  last 24 hours up to 3 months (default 2 months). hiring.cafe's own date
  filter is based on when *it* crawled a posting, so the scraper additionally
  enforces the cutoff against each job's estimated publish date; rows show
  "posted Nd ago".
- **Clear jobs** empties the scraped list (with a confirmation prompt).
  Statuses and application history in `data/state.json` are kept, and jobs
  that are scraped again pick their status back up. Clearing is refused while
  a scrape is running.

## Hosted dashboard (GitHub Pages)

The skill-trends dashboard is published as a static site on GitHub Pages. A
daily GitHub Action (`.github/workflows/refresh.yml`) re-scrapes hiring.cafe,
fetches full JD text for new jobs from the public ATS APIs, re-analyzes, commits
the refreshed `data/jobs.json` + `data/skill_stats.json`, and redeploys. The
description cache lives in the Actions cache (rebuildable, so losing it only
costs a refetch). `web/skills.html` detects when there's no backend and reads
`skill_stats.json` as a static file instead of `/api/skills`.

The interactive job tracker (`server.py` + `web/index.html`) is local-only.
`JOBBOT_PASSWORD` env var enables HTTP Basic auth on it if you ever expose it.

## Skill trends (JD analyzer)

Open **http://localhost:8765/skills** (or the "skill trends →" link in the
header). It shows what the scraped job descriptions actually ask for:

- **Top skills** — % of analyzed JDs mentioning each of ~120 tracked skills,
  filterable by category (IaC, CI/CD, Observability, …).
- **Head-to-head** — matchup cards for tooling rivalries (Terraform vs. Pulumi,
  EKS vs. ECS vs. GKE, GitHub Actions vs. GitLab CI vs. Jenkins, …).
- **Trend over time** — weekly/monthly % lines per skill, bucketed by each
  job's estimated publish date. Click chips to compare up to 8 skills.
- **Frequently paired** — skills that co-occur in the same JD.

**Refresh data** fetches full JD text for any jobs that don't have it yet
(via the public Greenhouse/Ashby/Lever board APIs — no auth needed), then
re-runs the analysis. The more scrapes accumulate over time, the longer and
more meaningful the trend timeline gets.

## Pieces

| Path | What it does |
| --- | --- |
| `bot/fetch_jobs.py` | Scrapes hiring.cafe search results (Next.js data API), filters to Ashby/Greenhouse/Lever + US full-time, writes `data/jobs.json`. Scrapes Remote, Hybrid, and Onsite as separate buckets (narrow with `--workplace Remote`). Queries are the `QUERIES` list at the top. |
| `server.py` | Web UI + JSON API (stdlib only, port 8765, override with `PORT`). |
| `web/index.html` | The frontend (single file, no build step). |
| `bot/apply.py` | Optional Playwright auto-apply bot; shares `data/state.json` with the UI, so its `SUBMITTED`/`SKIPPED`/`FAILED` results show up there too. Only applies to Remote jobs unless run with `--workplace all` (or a list like `Remote,Hybrid`). *Local-only: the apply bot, its ATS adapters, and the applicant profile are `.gitignore`d and not part of the public repo.* |
| `bot/fetch_descriptions.py` | Pulls full JD text for every job in `data/jobs.json` from the public ATS APIs into `data/descriptions.json`. Incremental; safe to re-run. |
| `bot/skills.py` | Skill taxonomy: ~120 canonical skills with alias regexes (case-sensitive guards for ambiguous tokens like `Go`, `Chef`, `Flux`). `extract_skills(text)` → set of names. |
| `bot/analyze_skills.py` | Runs extraction over all JDs, buckets by publish week/month, computes matchups and co-occurrence, writes `data/skill_stats.json`. |
| `web/skills.html` | The skill-trends dashboard (single file, no build step). |

## Data

- `data/jobs.json` — current scraped job list (rewritten by each scrape).
- `data/state.json` — per-URL status: `OPENED`, `SUBMITTED`, `SKIPPED`, `FAILED`,
  plus `opened_ts` when opened from the UI. Jobs with no entry show as `NEW`.
  Both the UI and `apply.py` merge their writes into this file, so they can run
  at the same time.
- `data/descriptions.json` — cached full JD text per job URL (~20 MB for 3k
  jobs). Jobs whose posting has been taken down are marked `gone`.
- `data/skill_stats.json` — output of `bot/analyze_skills.py`; what the
  `/skills` dashboard reads.
