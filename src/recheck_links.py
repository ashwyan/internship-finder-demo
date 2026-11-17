#!/usr/bin/env python3
"""Weekly: re-check links from the last 14 days of reports and list the ones that closed.
Skips anything in applied.txt. Writes output/<date>/recheck.txt."""
import re, sys, urllib.request, urllib.error
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent if HERE.name == "src" else HERE   # data (resume, state, output) lives at the repo root
today = date.today(); out = BASE / "output" / today.isoformat(); out.mkdir(parents=True, exist_ok=True)
af = BASE / "applied.txt"
applied = [l.strip().lower() for l in af.read_text().splitlines() if l.strip() and not l.startswith("#")] if af.exists() else []
items = {}
for d in range(14):
    day = BASE / "output" / (today - timedelta(days=d)).isoformat()
    for name in ("report.txt", "gemini_search.txt"):
        f = day / name
        if not f.exists(): continue
        title = ""
        for line in f.read_text().splitlines():
            if re.match(r"^\d+\. ", line): title = line
            m = re.search(r"(?:Job link|Apply|Link): (https?://\S+)", line)
            if m: items.setdefault(m.group(1), title)
def status(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as r:
            return "open" if r.status < 400 else f"HTTP {r.status}"
    except urllib.error.HTTPError as e: return "blocked" if e.code in (401, 403, 429) else f"CLOSED (HTTP {e.code})"
    except Exception: return "unchecked"
closed, checked = [], 0
for u, t in items.items():
    if any(a in (t + " " + u).lower() for a in applied): continue
    checked += 1
    if status(u).startswith("CLOSED"): closed.append(f"{t}\n   {u}")
lines = [f"Weekly link check {today}: {checked} postings re-checked, {len(closed)} look closed.", ""] + (closed or ["Nothing closed."])
(out / "recheck.txt").write_text("\n".join(lines) + "\n"); print(lines[0])
