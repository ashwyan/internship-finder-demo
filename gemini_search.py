#!/usr/bin/env python3
"""Gemini job SEARCH add-on. Only finds postings with Google Search; no rating, no resume sent.
One search per region, merged. Writes output/<date>/gemini_search.txt.
Key: ~/.config/internship/gemini_key or env GEMINI_API_KEY.  Exit 0 = written, 2 = skipped (no key), 1 = all searches failed."""
import json, os, re, sys, time, urllib.request, urllib.error
from datetime import date
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)

# ---- edit these to change what it searches ----
ROLES = "machine learning, AI, data science, data engineering and data analytics internships"
TERM = "Summer 2027 (or Spring 2027)"
REGIONS = {
    "California / Bay Area": "San Francisco Bay Area, Los Angeles, San Diego, Sacramento",
    "Pacific Northwest": "Seattle, Bellevue, Redmond, Portland",
    "Texas / Southwest / Mountain": "Austin, Dallas, Houston, Denver, Phoenix, Salt Lake City",
    "Midwest + Southeast": "Chicago, Minneapolis, Detroit, Columbus, Raleigh-Durham, Charlotte, Atlanta, Miami, Nashville",
    "Northeast + Mid-Atlantic": "Boston, Cambridge MA, New York City, New Jersey, Philadelphia, Pittsburgh, Washington DC, Northern Virginia",
    "Remote": "remote anywhere in the United States",
}
# Cities you like most come first in the file (lowercase pieces of the location text).
PREFERRED = ["san francisco", "bay area", "palo alto", "mountain view", "sunnyvale", "san jose", "seattle", "new york", "boston", "austin", "remote"]
BUDGET_SECONDS = 720   # stop searching after this long (free tier is slow) and write what we have
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# -----------------------------------------------
BASE = Path(__file__).resolve().parent
kf = Path.home() / ".config/internship/gemini_key"
key = os.environ.get("GEMINI_API_KEY") or (kf.read_text().strip() if kf.exists() else "")
if not key:
    print("gemini: no key, skipped"); sys.exit(2)
out = BASE / "output" / date.today().isoformat(); out.mkdir(parents=True, exist_ok=True)
main = (out / "report.txt").read_text().lower() if (out / "report.txt").exists() else ""

def load_lines(name):
    f = BASE / name
    return [l.strip().lower() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")] if f.exists() else []
applied = load_lines("applied.txt")          # one company or link per line; matching postings are skipped
seen_file = BASE / "gemini_seen.json"
try: seen_before = set(json.loads(seen_file.read_text()))
except Exception: seen_before = set()

def ask(places):
    prompt = (f"Use Google Search to find currently OPEN {ROLES} for {TERM}, posted or updated in the last 14 days, "
              f"located in: {places}. Prefer company career pages and job boards (Greenhouse, Lever, Workday, Handshake). "
              "Only list postings you actually found in search results; never invent one or guess a link. "
              "Output one posting per line, exactly: COMPANY | TITLE | LOCATION | URL . Up to 12 lines, no other text.")
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
    err = ""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            c = (d.get("candidates") or [{}])[0]
            t = "".join(p.get("text", "") for p in c.get("content", {}).get("parts", []))
            if t.strip(): return t, ""
            err = f"empty answer ({c.get('finishReason')})"
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code} {e.read()[:120]!r}"
            print(f"gemini: {err[:60]}, retry {attempt + 1}/2")
            if e.code in (400, 401, 403, 404): break
            time.sleep(10 * (attempt + 1))        # 429/5xx: back off and retry
        except Exception as e:
            err = f"failed: {e}"
    return "", err

def check(url):
    try:
        rq = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(rq, timeout=10) as r: return r.geturl(), ("link ok" if r.status < 400 else f"link HTTP {r.status}")
    except urllib.error.HTTPError as e: return url, ("link blocked (check by hand)" if e.code in (401, 403, 429) else f"link DEAD (HTTP {e.code})")
    except Exception: return url, "link not checked"

found, seen_urls, dropped, errors, ok_regions = {}, set(), 0, [], 0
why = {'not intern/senior title': 0, 'dead link': 0, 'duplicate': 0, 'seen on earlier day': 0, 'applied': 0, 'no link': 0}
T0 = time.time()
for region, places in REGIONS.items():
    if time.time() - T0 > BUDGET_SECONDS:
        errors.append(f"{region}: skipped, time budget used (free-tier Gemini is slow)"); continue
    print(f"gemini: searching {region}...")
    text, err = ask(places)
    if err: errors.append(f"{region}: {err}"); print(f"gemini: {region}: {err}"); continue
    ok_regions += 1
    for line in text.splitlines():
        p = [x.strip(" *`") for x in line.replace("**", "").strip().lstrip("-*0123456789. ").split("|")]
        if len(p) < 4 or not re.match(r"https?://", p[3]): why['no link'] += 1; continue
        if not re.search(r"intern|co-?op", p[1], re.I) or re.search(r"senior|staff|principal|\bphd\b", p[1], re.I): dropped += 1; why['not intern/senior title'] += 1; continue
        if any(a in (p[0] + " " + p[1] + " " + p[3]).lower() for a in applied): dropped += 1; why['applied'] += 1; continue
        url, st = check(p[3])
        if url in seen_before or p[3] in seen_before: dropped += 1; why['seen on earlier day'] += 1; continue
        if "DEAD" in st: dropped += 1; why['dead link'] += 1; continue
        if url in seen_urls: dropped += 1; why['duplicate'] += 1; continue
        seen_urls.add(url)
        found.setdefault(region, []).append((p, url, st))
    time.sleep(4)                                  # stay under free-tier rate limits
if ok_regions == 0:
    print("gemini: every region failed"); sys.exit(1)

total = sum(len(v) for v in found.values()); n_new = 0; res = []; i = 0
def rank(item):
    loc = item[0][2].lower()
    return 0 if any(c in loc for c in PREFERRED) else 1
for region, items in found.items():
    items.sort(key=rank)                          # preferred cities first inside each region
    res.append(f"=== {region} ===")
    for p, url, st in items:
        i += 1; dup = p[0].lower() in main; n_new += (not dup)
        res.append(f"{i}. {p[0]}, {p[1]}\n   Location: {p[2]}\n   Link: {url}\n   {st}" + ("\n   (company already in the main report)" if dup else "") + "\n")
head = [f"Gemini job search ({MODEL}, Google Search, whole US + remote). Not rated. Check each posting before applying.",
        f"{total} found, {n_new} from companies not in the main report. (dropped {dropped}: " + ", ".join(f"{v} {k}" for k, v in why.items() if v) + ")"]
if errors: head.append("Some regions failed today: " + "; ".join(errors))
(out / "gemini_search.txt").write_text("\n".join(head + [""] + (res or ["No postings found today."])) + "\n")
(out / ".gemini_count").write_text(str(n_new))
seen_file.write_text(json.dumps(sorted(seen_before | seen_urls)[-3000:]))
print(f"gemini: {total} found, {n_new} new companies, {len(errors)} regions failed"); sys.exit(0)
