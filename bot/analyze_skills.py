"""Analyze scraped job descriptions for skill trends → data/skill_stats.json.

Reads data/jobs.json (metadata incl. posted_at) and data/descriptions.json
(full JD text from bot/fetch_descriptions.py). Jobs without fetched text fall
back to hiring.cafe's pre-extracted technical_tools list when present.

Run:  .venv/bin/python -m bot.analyze_skills
"""
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations

from bot.skills import MATCHUPS, SKILLS, extract_skills

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_PATH = os.path.join(ROOT, "data", "jobs.json")
DESC_PATH = os.path.join(ROOT, "data", "descriptions.json")
OUT_PATH = os.path.join(ROOT, "data", "skill_stats.json")


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def parse_date(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def week_start(dt):
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def main():
    jobs = load(JOBS_PATH, [])
    descs = load(DESC_PATH, {})

    counts = Counter()
    weekly = defaultdict(Counter)     # skill -> {week: n}
    monthly = defaultdict(Counter)    # skill -> {month: n}
    week_totals = Counter()
    month_totals = Counter()
    pair_counts = Counter()
    analyzed = 0
    from_tools_only = 0

    # ignore stray ancient postings so the timeline stays honest
    floor = datetime.now(timezone.utc) - timedelta(days=200)

    for job in jobs:
        d = descs.get(job["url"], {})
        text = d.get("text") or ""
        skills = extract_skills(text) if text else set()
        if not text:
            tools = job.get("technical_tools") or []
            if tools:
                skills = extract_skills(", ".join(tools))
                from_tools_only += 1
            else:
                continue
        analyzed += 1
        posted = parse_date(job.get("posted_at"))
        wk = mo = None
        if posted and posted > floor:
            wk, mo = week_start(posted), posted.strftime("%Y-%m")
            week_totals[wk] += 1
            month_totals[mo] += 1
        for s in skills:
            counts[s] += 1
            if wk:
                weekly[s][wk] += 1
                monthly[s][mo] += 1
        for a, b in combinations(sorted(skills), 2):
            pair_counts[(a, b)] += 1

    skills_out = []
    for name, n in counts.most_common():
        skills_out.append({
            "name": name,
            "category": SKILLS[name][0],
            "count": n,
            "pct": round(100 * n / analyzed, 1) if analyzed else 0,
            "weekly": dict(weekly[name]),
            "monthly": dict(monthly[name]),
        })

    matchups_out = []
    for title, names in MATCHUPS:
        entries = [{"name": n, "count": counts.get(n, 0),
                    "pct": round(100 * counts.get(n, 0) / analyzed, 1) if analyzed else 0}
                   for n in names]
        entries.sort(key=lambda e: -e["count"])
        matchups_out.append({"title": title, "skills": entries})

    top_names = {s["name"] for s in skills_out[:40]}
    pairs_out = [[a, b, n] for (a, b), n in pair_counts.most_common(300)
                 if a in top_names and b in top_names][:60]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_jobs": len(jobs),
        "analyzed": analyzed,
        "with_full_text": analyzed - from_tools_only,
        "weeks": sorted(week_totals),
        "months": sorted(month_totals),
        "week_totals": dict(week_totals),
        "month_totals": dict(month_totals),
        "skills": skills_out,
        "matchups": matchups_out,
        "pairs": pairs_out,
    }
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f)
    os.replace(tmp, OUT_PATH)

    print(f"analyzed {analyzed}/{len(jobs)} jobs "
          f"({analyzed - from_tools_only} full JDs, {from_tools_only} from technical_tools)")
    print("top 15:")
    for s in skills_out[:15]:
        print(f"  {s['name']:<22} {s['count']:>5}  {s['pct']}%")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
