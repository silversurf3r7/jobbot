"""Fetch DevOps-family jobs from hiring.cafe and keep ones on automatable ATS platforms."""
import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Focused strictly on the four requested role families (DevOps, Terraform, SRE,
# Platform Engineer) with seniority/tech variations to surface as many distinct
# boards as possible — no unrelated keyword families.
QUERIES = [
    "devops engineer", "devops", "senior devops engineer", "staff devops engineer",
    "lead devops engineer", "principal devops engineer", "devops",
    "terraform", "terraform engineer", "terraform devops",
    "site reliability engineer", "sre", "senior site reliability engineer",
    "staff site reliability engineer", "principal site reliability engineer",
    "platform engineer", "platform engineering", "senior platform engineer",
    "staff platform engineer", "principal platform engineer", "lead platform engineer",
    "devops platform engineer", "aws devops engineer", "azure devops engineer",
    "gcp devops engineer", "kubernetes devops engineer", "cloud platform engineer",
    "infrastructure platform engineer", "reliability engineer", "sre platform engineer",
]

SUPPORTED_SOURCES = {"grnhse", "ashby", "lever", "workable", "breezy"}
MAX_PAGES_PER_QUERY = 40


def get_build_id(sess):
    r = sess.get("https://hiring.cafe/", timeout=30)
    r.raise_for_status()
    m = re.search(r'"buildId":"([^"]+)"', r.text)
    if not m:
        m = re.search(r'/_next/data/([^/]+)/', r.text)
    if not m:
        raise RuntimeError("could not find Next.js buildId on homepage")
    return m.group(1)


def search_page(sess, build_id, query, page, workplace_type, days):
    state = {
        "searchQuery": query,
        "workplaceTypes": [workplace_type],
        "dateFetchedPastNDays": days,
    }
    url = (f"https://hiring.cafe/_next/data/{build_id}/index.json?"
           f"searchState={urllib.parse.quote(json.dumps(state))}&page={page}")
    r = sess.get(url, headers={"x-nextjs-data": "1"}, timeout=30)
    if r.status_code != 200:
        return None
    pp = r.json().get("pageProps", {})
    return pp


def greenhouse_canonical(hit):
    """Build a canonical Greenhouse-hosted application URL."""
    apply_url = hit.get("apply_url") or ""
    board = hit.get("board_token") or ""
    m = re.search(r'gh_jid=(\d+)', apply_url)
    if not m:
        m = re.search(r'greenhouse\.io/(?:embed/job_app\?token=\d+|[^/]+/jobs/(\d+))', apply_url)
        m = re.search(r'/jobs/(\d+)', apply_url)
    if m and board:
        return f"https://job-boards.greenhouse.io/{board}/jobs/{m.group(1)}"
    if "greenhouse.io" in apply_url:
        return apply_url
    return None


def normalize(hit):
    src = hit.get("source")
    if src not in SUPPORTED_SOURCES:
        return None
    v5 = hit.get("v5_processed_job_data") or {}
    comp = hit.get("enriched_company_data") or {}
    info = hit.get("job_information") or {}

    # Filters: US, no clearance, not entry-level/executive
    countries = v5.get("workplace_countries") or []
    if countries and not ({"US", "United States"} & set(countries)):
        return None
    clearance = v5.get("security_clearance")
    if clearance and str(clearance).lower() not in ("none", "null", ""):
        return None
    if v5.get("seniority_level") in ("Entry Level", "Executive Level"):
        return None
    commitment = v5.get("commitment") or []
    if commitment and "Full Time" not in commitment:
        return None

    apply_url = hit.get("apply_url") or ""
    if src == "grnhse":
        url = greenhouse_canonical(hit)
        if not url:
            return None
    elif src == "ashby":
        if "jobs.ashbyhq.com" not in apply_url:
            return None
        url = apply_url.split("?")[0].rstrip("/")
        if not url.endswith("/application"):
            url += "/application"
    elif src == "lever":
        if "jobs.lever.co" not in apply_url:
            return None
        url = apply_url.split("?")[0].rstrip("/")
        if not url.endswith("/apply"):
            url += "/apply"
    elif src == "workable":
        if "workable.com" not in apply_url:
            return None
        url = apply_url.split("?")[0]
    elif src == "breezy":
        if "breezy.hr" not in apply_url:
            return None
        url = apply_url.split("?")[0]
    else:
        return None

    return {
        "id": hit.get("id"),
        "source": src,
        "board_token": hit.get("board_token"),
        "url": url,
        "original_apply_url": apply_url,
        "title": (info.get("title") or "").strip(),
        "company": comp.get("name") or v5.get("company_name") or "",
        "location": v5.get("formatted_workplace_location") or "",
        "workplace_type": v5.get("workplace_type") or "",
        "seniority": v5.get("seniority_level") or "",
        "comp_min": v5.get("yearly_min_compensation"),
        "comp_max": v5.get("yearly_max_compensation"),
        "posted_at": v5.get("estimated_publish_date"),
        "technical_tools": v5.get("technical_tools") or [],
        "requirements_summary": v5.get("requirements_summary") or "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workplace", default="Remote,Hybrid,Onsite",
                    help="comma-separated hiring.cafe workplace types to scrape")
    ap.add_argument("--query", default="",
                    help="comma-separated search queries; blank = built-in QUERIES list")
    ap.add_argument("--days", type=int, default=61,
                    help="only keep jobs published in the last N days")
    args = ap.parse_args()
    # hiring.cafe's dateFetchedPastNDays filters by when IT last crawled a job,
    # not when the job was published — so ask for a slightly wider crawl window
    # and enforce the real publish-date cutoff ourselves below.
    fetch_days = max(args.days, 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    workplace_types = [w.strip() for w in args.workplace.split(",") if w.strip()]
    queries = [q.strip() for q in args.query.split(",") if q.strip()] or QUERIES

    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    build_id = get_build_id(sess)
    print(f"buildId: {build_id}")

    jobs, seen = [], set()
    raw_counts = {}
    too_old = 0
    # Each workplace type is scraped as its own bucket so page caps on broad
    # queries don't crowd out remote results.
    for wt in workplace_types:
        for q in queries:
            total_seen = 0
            for page in range(MAX_PAGES_PER_QUERY):
                pp = search_page(sess, build_id, q, page, wt, fetch_days)
                if pp is None:
                    print(f"  [{wt} | {q}] page {page}: request failed, stopping query")
                    break
                hits = pp.get("ssrHits") or []
                if not hits:
                    break
                total_seen += len(hits)
                for h in hits:
                    raw_counts[h.get("source")] = raw_counts.get(h.get("source"), 0) + 1
                    j = normalize(h)
                    if not j:
                        continue
                    key = j["url"]
                    if key in seen:
                        continue
                    if j.get("posted_at"):
                        try:
                            posted = datetime.fromisoformat(j["posted_at"].replace("Z", "+00:00"))
                            if posted < cutoff:
                                too_old += 1
                                continue
                        except ValueError:
                            pass
                    seen.add(key)
                    j["search_query"] = q
                    jobs.append(j)
                if pp.get("ssrIsLastPage"):
                    break
                time.sleep(0.4)
            print(f"[{wt} | {q}] scanned ~{total_seen} hits, running unique automatable total: {len(jobs)}")

    from collections import Counter
    print(f"\ndropped {too_old} jobs published more than {args.days} days ago")
    print("raw source distribution:", dict(sorted(raw_counts.items(), key=lambda x: -x[1])))
    print("kept by source:", dict(Counter(j['source'] for j in jobs)))
    print("kept by workplace_type:", dict(Counter(j['workplace_type'] for j in jobs)))

    # Merge into the existing list (dedupe by URL) so scraping one keyword
    # doesn't wipe jobs found by earlier scrapes.
    try:
        with open("data/jobs.json") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []
    by_url = {j["url"]: j for j in existing}
    added = refreshed = 0
    for j in jobs:
        old = by_url.get(j["url"])
        if old:
            if old.get("search_query"):
                j["search_query"] = old["search_query"]  # keep original tag
            by_url[j["url"]] = {**old, **j}
            refreshed += 1
        else:
            by_url[j["url"]] = j
            added += 1
    merged = list(by_url.values())
    with open("data/jobs.json", "w") as f:
        json.dump(merged, f, indent=1)
    print(f"\nwrote {len(merged)} jobs to data/jobs.json "
          f"({added} new, {refreshed} refreshed, {len(existing) - refreshed} kept from earlier scrapes)")


if __name__ == "__main__":
    main()
