"""Job helper web UI: browse scraped hiring.cafe jobs, open applications, track status.

Run with:  .venv/bin/python server.py   then open http://localhost:8765
Reads data/jobs.json (written by bot/fetch_jobs.py) and shares data/state.json
with bot/apply.py, so statuses from the auto-apply bot show up here too.
"""
import base64
import hmac
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
JOBS_PATH = os.path.join(ROOT, "data", "jobs.json")
STATE_PATH = os.path.join(ROOT, "data", "state.json")
SKILL_STATS_PATH = os.path.join(ROOT, "data", "skill_stats.json")
WEB_DIR = os.path.join(ROOT, "web")
PORT = int(os.environ.get("PORT", "8765"))
# When set, every request must carry HTTP Basic auth with this password
# (any username). Used when exposing the server through a public tunnel.
PASSWORD = os.environ.get("JOBBOT_PASSWORD", "")

VALID_STATUSES = {"NEW", "OPENED", "SUBMITTED", "SKIPPED", "FAILED"}

state_lock = threading.Lock()
scrape_lock = threading.Lock()
scrape_info = {"running": False, "started": None, "finished": None, "rc": None, "tail": [],
               "query": "", "days": 61}
analyze_lock = threading.Lock()
analyze_info = {"running": False, "started": None, "finished": None, "rc": None,
                "tail": [], "step": ""}


def now():
    return datetime.now().isoformat(timespec="seconds")


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE_PATH)


def jobs_with_state():
    jobs = load_json(JOBS_PATH, [])
    state = load_json(STATE_PATH, {})
    out = []
    for j in jobs:
        s = state.get(j["url"], {})
        j = dict(j)
        j["status"] = s.get("status") or "NEW"
        j["status_ts"] = s.get("ts")
        j["opened_ts"] = s.get("opened_ts")
        j["detail"] = s.get("detail") or ""
        out.append(j)
    return out


def find_job(url):
    for j in load_json(JOBS_PATH, []):
        if j["url"] == url:
            return j
    return None


def mark_opened(url):
    with state_lock:
        state = load_json(STATE_PATH, {})
        entry = state.get(url)
        if entry is None:
            job = find_job(url)
            if job is None:
                return None
            entry = {"status": "OPENED", "detail": "opened from web UI",
                     "company": job["company"], "title": job["title"],
                     "source": job["source"], "ts": now()}
        elif entry.get("status") in (None, "", "NEW", "OPENED"):
            entry["status"] = "OPENED"
            entry["ts"] = now()
        entry["opened_ts"] = now()
        state[url] = entry
        save_state(state)
        return entry


def set_status(url, status):
    if status not in VALID_STATUSES:
        return None
    with state_lock:
        state = load_json(STATE_PATH, {})
        entry = state.get(url)
        if status == "NEW":
            # Reset: forget the status but keep nothing else around.
            if url in state:
                del state[url]
                save_state(state)
            return {"status": "NEW"}
        if entry is None:
            job = find_job(url)
            if job is None:
                return None
            entry = {"company": job["company"], "title": job["title"], "source": job["source"]}
        entry["status"] = status
        entry["detail"] = "set from web UI"
        entry["ts"] = now()
        state[url] = entry
        save_state(state)
        return entry


def start_scrape(query="", days=61):
    days = max(1, min(int(days or 61), 92))  # cap at ~3 months
    with scrape_lock:
        if scrape_info["running"]:
            return False
        scrape_info.update(running=True, started=now(), finished=None, rc=None, tail=[],
                           query=query, days=days)

    cmd = [sys.executable, "-u", os.path.join(ROOT, "bot", "fetch_jobs.py"), "--days", str(days)]
    if query:
        cmd += ["--query", query]

    def worker():
        try:
            p = subprocess.Popen(
                cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                scrape_info["tail"] = (scrape_info["tail"] + [line.rstrip()])[-20:]
            p.wait()
            rc = p.returncode
        except Exception as e:  # noqa: BLE001
            scrape_info["tail"] = scrape_info["tail"] + [f"error: {e}"]
            rc = -1
        scrape_info.update(running=False, finished=now(), rc=rc)

    threading.Thread(target=worker, daemon=True).start()
    return True


def start_analyze(fetch=True):
    """Refresh skill stats: optionally fetch missing JD texts, then re-analyze."""
    with analyze_lock:
        if analyze_info["running"]:
            return False
        analyze_info.update(running=True, started=now(), finished=None, rc=None,
                            tail=[], step="starting")

    steps = []
    if fetch:
        steps.append(("fetching descriptions",
                      [sys.executable, "-u", "-m", "bot.fetch_descriptions"]))
    steps.append(("analyzing skills",
                  [sys.executable, "-u", "-m", "bot.analyze_skills"]))

    def worker():
        rc = 0
        for step_name, cmd in steps:
            analyze_info["step"] = step_name
            try:
                p = subprocess.Popen(
                    cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in p.stdout:
                    analyze_info["tail"] = (analyze_info["tail"] + [line.rstrip()])[-20:]
                p.wait()
                rc = p.returncode
            except Exception as e:  # noqa: BLE001
                analyze_info["tail"] = analyze_info["tail"] + [f"error: {e}"]
                rc = -1
            if rc != 0:
                break
        analyze_info.update(running=False, finished=now(), rc=rc, step="done")

    threading.Thread(target=worker, daemon=True).start()
    return True


def clear_jobs():
    """Empty the scraped job list. Application history in state.json is kept."""
    with scrape_lock:
        if scrape_info["running"]:
            return None
        n = len(load_json(JOBS_PATH, []))
        tmp = JOBS_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump([], f)
        os.replace(tmp, JOBS_PATH)
        return n


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def check_auth(self):
        if not PASSWORD:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(auth[6:]).decode().partition(":")
            except Exception:  # noqa: BLE001
                given = ""
            if hmac.compare_digest(given, PASSWORD):
                return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="jobbot"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self.check_auth():
            return
        path = self.path.split("?")[0]
        if path == "/api/jobs":
            self.send_json(jobs_with_state())
        elif path == "/api/scrape":
            self.send_json(scrape_info)
        elif path == "/api/skills":
            self.send_json(load_json(SKILL_STATS_PATH, {}))
        elif path == "/api/skills/status":
            self.send_json(analyze_info)
        elif path in ("/", "/index.html", "/skills"):
            page = "skills.html" if path == "/skills" else "index.html"
            try:
                with open(os.path.join(WEB_DIR, page), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_json({"error": f"web/{page} missing"}, 500)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.check_auth():
            return
        path = self.path.split("?")[0]
        body = self.read_body()
        if path == "/api/open":
            entry = mark_opened(body.get("url") or "")
            if entry is None:
                self.send_json({"error": "unknown job url"}, 404)
            else:
                self.send_json(entry)
        elif path == "/api/status":
            entry = set_status(body.get("url") or "", body.get("status") or "")
            if entry is None:
                self.send_json({"error": "unknown job url or bad status"}, 400)
            else:
                self.send_json(entry)
        elif path == "/api/scrape":
            try:
                days = int(body.get("days") or 61)
            except (TypeError, ValueError):
                days = 61
            started = start_scrape((body.get("query") or "").strip(), days)
            self.send_json({"started": started, **scrape_info})
        elif path == "/api/skills/refresh":
            started = start_analyze(fetch=bool(body.get("fetch", True)))
            self.send_json({"started": started, **analyze_info})
        elif path == "/api/clear":
            n = clear_jobs()
            if n is None:
                self.send_json({"error": "scrape in progress, try again when it finishes"}, 409)
            else:
                self.send_json({"cleared": n})
        else:
            self.send_json({"error": "not found"}, 404)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"jobbot UI on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
