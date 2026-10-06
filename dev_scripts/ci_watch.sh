#!/usr/bin/env bash
# Follow a Forgejo Actions job: prints status changes, steps and new log lines until the run ends.
# Usage: dev_scripts/ci_watch.sh <run> [job=0] [interval=20]   (token: FORGEJO_TOKEN in .env)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

run=${1:?run number}
job=${2:-0}
every=${3:-20}
host=${FORGEJO_HOST:-https://git.giacomofurlan.name}
repo=${FORGEJO_REPO:-elegos/json2json-mapping-engine}

exec python3 -I - "$host/$repo/actions/runs/$run/jobs/$job/attempt/${ATTEMPT:-1}" "$every" <<'PY'
import json, os, sys, time, urllib.request

url, every = sys.argv[1], int(sys.argv[2])
cursors: dict[int, int] = {}
last = None
while True:
    body = json.dumps({"logCursors": [{"step": s, "cursor": c, "expanded": True} for s, c in cursors.items()] or [{"step": 0, "cursor": 0, "expanded": True}]}).encode()
    req = urllib.request.Request(url, body, {"Authorization": f"token {os.environ['FORGEJO_TOKEN']}", "Content-Type": "application/json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:  # transient network/server error: keep polling
        print(f"poll error: {e}", flush=True)
        time.sleep(every)
        continue
    run, job = d["state"]["run"], d["state"]["currentJob"]
    steps = job["steps"]
    state = (run["status"], [(s["summary"], s["status"]) for s in steps])
    if state != last:
        print(f"[{run['status']}] " + ", ".join(f"{s['summary']}={s['status']}" for s in steps), flush=True)
        last = state
    for sl in d["logs"]["stepsLog"]:
        for line in sl["lines"]:
            print(line["message"], flush=True)
        cursors[sl["step"]] = sl["cursor"]
    for i, s in enumerate(steps):
        if s["status"] != "waiting":
            cursors.setdefault(i, 0)
    if run["done"]:
        print(f"DONE: {run['status']}", flush=True)
        break
    time.sleep(every)
PY
