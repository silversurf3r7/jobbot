"""Fetch full job-description text for jobs in data/jobs.json via public ATS APIs.

Greenhouse: boards-api.greenhouse.io (one request per job)
Ashby:      api.ashbyhq.com posting-api (one request per org, covers all its jobs)
Lever:      api.lever.co/v0/postings (one request per job)

Results go to data/descriptions.json keyed by job URL:
  {url: {"status": "ok"|"gone"|"error", "fetched_at": iso, "text": "..."}}

Incremental: already-fetched "ok"/"gone" entries are skipped; "error" entries are
retried. Run:  .venv/bin/python -m bot.fetch_descriptions [--limit N]
"""
import argparse
import html
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_PATH = os.path.join(ROOT, "data", "jobs.json")
DESC_PATH = os.path.join(ROOT, "data", "descriptions.json")
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")}

lock = threading.Lock()


def strip_html(raw):
    """HTML → readable plain text."""
    s = html.unescape(raw or "")
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"</?(p|br|li|ul|ol|div|h[1-6]|tr)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def fetch_greenhouse(sess, job):
    m = re.search(r"/jobs/(\d+)", job["url"])
    board = job.get("board_token")
    if not (m and board):
        return "error", ""
    r = sess.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{m.group(1)}",
                 headers=UA, timeout=25)
    if r.status_code == 404:
        return "gone", ""
    r.raise_for_status()
    d = r.json()
    return "ok", strip_html(d.get("content", ""))


def fetch_lever(sess, job):
    m = re.search(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})", job["url"])
    if not m:
        return "error", ""
    r = sess.get(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}",
                 headers=UA, timeout=25)
    if r.status_code == 404:
        return "gone", ""
    r.raise_for_status()
    d = r.json()
    parts = [d.get("description") or ""]
    for lst in d.get("lists") or []:
        parts.append(lst.get("text") or "")
        parts.append(lst.get("content") or "")
    parts.append(d.get("additional") or "")
    return "ok", strip_html("\n".join(parts))


class AshbyBoards:
    """Ashby's posting API is per-org; cache each org's board across its jobs."""

    def __init__(self, sess):
        self.sess = sess
        self.boards = {}
        self.board_lock = threading.Lock()

    def get_board(self, org):
        with self.board_lock:
            if org in self.boards:
                return self.boards[org]
        try:
            r = self.sess.get(f"https://api.ashbyhq.com/posting-api/job-board/{org}",
                              headers=UA, timeout=25)
            if r.status_code == 404:
                board = {}
            else:
                r.raise_for_status()
                board = {j.get("id"): j for j in r.json().get("jobs", [])}
        except Exception:
            board = None  # transient failure: don't cache
        with self.board_lock:
            if board is not None:
                self.boards[org] = board
        return board

    def fetch(self, job):
        m = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})", job["url"])
        if not m:
            return "error", ""
        board = self.get_board(m.group(1))
        if board is None:
            return "error", ""
        posting = board.get(m.group(2))
        if not posting:
            return "gone", ""
        return "ok", strip_html(posting.get("descriptionHtml", ""))


def save(descs):
    tmp = DESC_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(descs, f)
    os.replace(tmp, DESC_PATH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max jobs to fetch this run (0 = all)")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    with open(JOBS_PATH) as f:
        jobs = json.load(f)
    try:
        with open(DESC_PATH) as f:
            descs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        descs = {}

    todo = [j for j in jobs if descs.get(j["url"], {}).get("status") not in ("ok", "gone")]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(jobs)} jobs, {len(descs)} already fetched, {len(todo)} to fetch")

    sess = requests.Session()
    ashby = AshbyBoards(sess)
    fetchers = {"grnhse": lambda j: fetch_greenhouse(sess, j),
                "lever": lambda j: fetch_lever(sess, j),
                "ashby": ashby.fetch}
    done = [0]

    def work(job):
        fn = fetchers.get(job["source"])
        if fn is None:
            return job["url"], "error", ""
        try:
            status, text = fn(job)
        except Exception:
            status, text = "error", ""
        return job["url"], status, text

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(work, j) for j in todo]
        for fut in as_completed(futures):
            url, status, text = fut.result()
            with lock:
                descs[url] = {"status": status, "text": text,
                              "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                done[0] += 1
                if done[0] % 100 == 0:
                    save(descs)
                    ok = sum(1 for d in descs.values() if d["status"] == "ok")
                    print(f"  {done[0]}/{len(todo)} fetched ({ok} ok total)")
            time.sleep(0.05)

    save(descs)
    from collections import Counter
    counts = Counter(d["status"] for d in descs.values())
    print(f"done: {dict(counts)}  → {DESC_PATH}")


if __name__ == "__main__":
    main()
