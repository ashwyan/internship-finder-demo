#!/usr/bin/env python3
"""Internship finder. Free, runs on your computer, no API key.

Each run it writes one report with:
1. Open ML, AI, data science and data engineering internships, with the job link
   and LinkedIn search links (alumni, team members, recruiters).
2. Small and mid-size companies that are hiring, where you can email the CEO.

Run:  python3 internship_finder.py
Needs: Python 3.8 or newer. Ollama with qwen3:4b is optional and improves the ratings.
"""

import argparse
import html
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent if HERE.name == "src" else HERE   # data (resume, state, output) lives at the repo root
RESUME_FILE = BASE / "master_resume.json"
STATE_FILE = BASE / "state.json"
OUT_DIR = BASE / "output"
SCHOOL = "Example University"   # used for the alumni LinkedIn search link

# ---------------------------------------------------------------- settings
LISTING_URLS = [
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json",
]
TERMS = {"Summer 2027", "Spring 2027"}
MAX_AGE_DAYS = 14
TOP_N_REPORT = 12
MAX_SMALL_COMPANIES = 8

# Optional: add company board names to also check them directly.
# Greenhouse name is the part after boards.greenhouse.io/ in the careers URL.
# Lever name is the part after jobs.lever.co/ in the careers URL.
# Company boards read straight from the companies' public job APIs (direct links, no middleman).
# Add more: the Greenhouse name is the part after boards.greenhouse.io/, Lever after jobs.lever.co/, Ashby after jobs.ashbyhq.com/.
GREENHOUSE_BOARDS = [
    "anthropic", "databricks", "scaleai", "stripe", "airbnb", "figma", "coinbase", "instacart", "lyft",
    "pinterest", "reddit", "robinhood", "samsara", "duolingo", "cloudflare", "datadog", "mongodb",
    "twilio", "roblox", "brex", "verkada", "waymo", "nuro", "neuralink",
]
LEVER_BOARDS = ["palantir", "zoox"]
ASHBY_BOARDS = ["openai", "ramp", "notion", "perplexity", "cohere"]
BOARD_NAMES = {"scaleai": "Scale AI", "openai": "OpenAI", "mongodb": "MongoDB", "datadog": "Datadog",
               "neuralink": "Neuralink", "waymo": "Waymo", "zoox": "Zoox", "ramp": "Ramp"}
# A second community list. Its links go through the maintainer's redirect domain, so we resolve the ones we show.
VANSH_URL = "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json"
USE_VANSH = True

BAY_AREA = [
    "san francisco", "palo alto", "mountain view", "sunnyvale", "san jose", "santa clara",
    "menlo park", "redwood city", "oakland", "berkeley", "fremont", "cupertino",
    "south san francisco", "san mateo", "foster city", "emeryville", "los gatos",
    "milpitas", "bay area", "san carlos", "burlingame", "los altos", "campbell",
]
OTHER_TARGETS = [
    "remote", "austin", "seattle", "bellevue", "redmond", "kirkland", "raleigh", "durham",
    "cary", "chapel hill", "morrisville", "boston", "cambridge, ma", "waltham", "somerville",
    # more of the US (open to relocate)
    "new york", "brooklyn", "hoboken", "jersey city", "new jersey", "princeton", "stamford",
    "chicago", "minneapolis", "detroit", "ann arbor", "columbus", "indianapolis", "st. louis",
    "atlanta", "charlotte", "nashville", "miami", "tampa", "orlando",
    "dallas", "houston", "plano", "denver", "boulder", "salt lake", "phoenix", "tempe",
    "los angeles", "santa monica", "irvine", "san diego", "portland, or", "sacramento",
    "washington, dc", "arlington, va", "mclean", "reston", "baltimore", "philadelphia", "pittsburgh",
]

TITLE_INCLUDE = re.compile(
    r"machine learning|\bml\b|\bai\b|artificial intelligence|data scien|data engineer|data analy|"
    r"analytics|\bnlp\b|\bllm|deep learning|research engineer|applied scientist|mlops|"
    r"computer vision|generative|\bgenai\b",
    re.I,
)
TITLE_EXCLUDE = re.compile(
    r"hardware|electrical|mechanical|civil|manufactur|supply chain|sales|marketing|recruit|"
    r"phd|ph\.d|legal|accounting|finance|\bsenior\b|\bstaff\b|\bprincipal\b",
    re.I,
)
ML_TITLE = re.compile(
    r"machine learning|\bml\b|deep learning|applied scientist|mlops|computer vision|\bnlp\b|"
    r"\bllm|generative|\bgenai\b|\bai\b|artificial intelligence",
    re.I,
)

FAMILIES = {
    "ml": r"machine learning|\bml\b|deep learning|pytorch|tensorflow|model|neural|evaluation|statistic|causal|research|scientist",
    "nlp": r"\bnlp\b|\bllm|language model|generative|gen ?ai|\bai\b|\brag\b|chatbot|conversation|transcription|retrieval|langchain",
    "data": r"data (scien|engineer|analy)|analytics|\betl\b|pipeline|\bsql\b|postgres|database|warehouse|time.series|spark|dbt",
    "swe": r"software|full.?stack|backend|front.?end|react|\bapi\b|android|mobile|\bweb\b|\bui\b|\bux\b",
    "infra": r"infrastructure|platform|devops|mlops|cloud|docker|kubernetes|linux|\bgpu\b|distributed",
}
FAMILY_SKILLS = {
    "ml": ["pytorch", "scikit-learn", "statistical modeling", "causal inference", "model evaluation", "time-series analysis", "python"],
    "nlp": ["nlp", "langchain", "faiss", "pytorch", "python"],
    "data": ["sql", "r", "postgresql", "etl pipelines", "time-series analysis", "python", "statistical modeling"],
    "swe": ["react", "rest apis", "supabase", "java", "kotlin", "ui/ux", "git", "github", "c++"],
    "infra": ["docker", "linux", "ssh", "tailscale", "bash", "git"],
}
# Local AI through Ollama (free, runs on your computer). See README.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen3:4b")
KEEP_DAYS = 30        # report folders older than this are deleted after each run
LLM_CANDIDATES = 15   # how many top keyword matches the AI reads in full


# ---------------------------------------------------------------- fetching
def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 internship-finder"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url):
    return json.loads(fetch(url).decode("utf-8", "ignore"))


def page_text(url):
    """Best effort: plain text of a posting page. Many pages need JavaScript and return little."""
    try:
        raw = fetch(url, timeout=15).decode("utf-8", "ignore")
    except Exception:
        return ""
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw))[:20000]


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html.unescape(html.unescape(s or ""))))


def load_simplify():
    out, loaded = [], 0
    for url in LISTING_URLS:
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"Could not load {url}: {exc}", file=sys.stderr)
            continue
        loaded += 1
        for x in data:
            if not x.get("active") or not x.get("is_visible", True):
                continue
            if not TERMS.intersection(x.get("terms") or []):
                continue
            degrees = [d.lower() for d in (x.get("degrees") or [])]
            if degrees and not any("bachelor" in d for d in degrees):
                continue
            out.append(
                {
                    "id": x.get("id") or x.get("url"),
                    "company": x.get("company_name", ""),
                    "title": x.get("title", ""),
                    "category": x.get("category", ""),
                    "locations": x.get("locations") or [],
                    "url": x.get("url", ""),
                    "updated": max(x.get("date_posted") or 0, x.get("date_updated") or 0),
                    "sponsorship": x.get("sponsorship", ""),
                    "description": "",
                    "source": "Simplify",
                }
            )
    if not loaded:
        sys.exit("Could not download the internship list. Check your internet connection and try again.")
    return out


def load_vanshb03():
    if not USE_VANSH:
        return []
    try:
        data = fetch_json(VANSH_URL)
    except Exception as exc:
        print(f"Could not load second list: {exc}", file=sys.stderr)
        return []
    return [
        {
            "id": "vb-" + str(x.get("id") or x.get("url")),
            "company": x.get("company_name", ""),
            "title": x.get("title", ""),
            "category": "",
            "locations": x.get("locations") or [],
            "url": x.get("url", ""),
            "updated": max(x.get("date_posted") or 0, x.get("date_updated") or 0),
            "sponsorship": x.get("sponsorship", ""),
            "description": "",
            "source": "vanshb03 list",
        }
        for x in data
        if x.get("active") and x.get("is_visible", True) and x.get("season") in ("Summer", "Spring", "Spring/Summer")
    ]


def resolve_url(url):
    """Follow a redirect to the real job page. On any problem keep the original link."""
    if "go.vansh.nyc" not in url:
        return url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 internship-finder"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.geturl()
    except Exception:
        return url


INTERN_RE = re.compile(r"\bintern|co-?op\b", re.I)


def _pretty(slug):
    return BOARD_NAMES.get(slug, slug.replace("-", " ").title())


def _greenhouse(slug):
    # No content=true: it is huge. The AI step reads the posting page for the few it needs.
    jobs = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs").get("jobs", [])
    out = []
    for j in jobs:
        if not INTERN_RE.search(j.get("title", "")):
            continue
        try:
            ts = datetime.fromisoformat(j["updated_at"].replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = time.time()
        out.append({"id": f"gh-{slug}-{j.get('id')}", "company": _pretty(slug), "title": j.get("title", ""),
                    "category": "", "locations": [(j.get("location") or {}).get("name", "")],
                    "url": j.get("absolute_url", ""), "updated": ts, "sponsorship": "", "description": "",
                    "source": "Greenhouse"})
    return out


def _lever(slug):
    out = []
    for j in fetch_json(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        if not INTERN_RE.search(j.get("text", "")):
            continue
        out.append({"id": f"lv-{slug}-{j.get('id')}", "company": _pretty(slug), "title": j.get("text", ""),
                    "category": (j.get("categories") or {}).get("team", ""),
                    "locations": [(j.get("categories") or {}).get("location", "")],
                    "url": j.get("hostedUrl", ""), "updated": (j.get("createdAt") or time.time() * 1000) / 1000,
                    "sponsorship": "", "description": (j.get("descriptionPlain") or "")[:20000], "source": "Lever"})
    return out


def _ashby(slug):
    out = []
    for j in fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}").get("jobs", []):
        if not j.get("isListed", True) or not (INTERN_RE.search(j.get("title", "")) or j.get("employmentType") == "Intern"):
            continue
        try:
            ts = datetime.fromisoformat(j["publishedAt"].replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = time.time()
        locs = [j.get("location", "")] + [x.get("location", "") for x in (j.get("secondaryLocations") or []) if isinstance(x, dict)]
        if j.get("workplaceType") == "Remote":
            locs.append("Remote")
        out.append({"id": f"ab-{slug}-{j.get('id')}", "company": _pretty(slug), "title": j.get("title", ""),
                    "category": j.get("team", ""), "locations": [l for l in locs if l],
                    "url": j.get("jobUrl", ""), "updated": ts, "sponsorship": "",
                    "description": (j.get("descriptionPlain") or "")[:20000], "source": "Ashby"})
    return out


def load_boards():
    """Read every company board at the same time. One board failing never stops the others."""
    from concurrent.futures import ThreadPoolExecutor

    tasks = [(f, s) for f, boards in ((_greenhouse, GREENHOUSE_BOARDS), (_lever, LEVER_BOARDS), (_ashby, ASHBY_BOARDS)) for s in boards]

    def run(t):
        fn, slug = t
        try:
            return fn(slug)
        except Exception as exc:
            print(f"{fn.__name__.strip('_')} {slug} failed: {exc}", file=sys.stderr)
            return []

    with ThreadPoolExecutor(8) as ex:
        return [j for res in ex.map(run, tasks) for j in res]


# ---------------------------------------------------------------- rating
def place_score(locations):
    text = " | ".join(locations).lower()
    if any(p in text for p in BAY_AREA):
        return 2
    if any(p in text for p in OTHER_TARGETS):
        return 1
    return None


def rate(job):
    title = job["title"]
    if not TITLE_INCLUDE.search(title) or TITLE_EXCLUDE.search(title):
        return None
    where = place_score(job["locations"])
    if where is None:
        return None
    score = where
    if ML_TITLE.search(title) or re.search(r"data scien", title, re.I):
        score += 5
    elif re.search(r"data engineer", title, re.I):
        score += 4
    elif re.search(r"data analy|analytics", title, re.I):
        score += 3
    else:
        score += 2
    if re.search(r"ai/ml|data science|machine learning", job["category"], re.I):
        score += 2
    return score


def fit_label(score):
    return "Strong" if score >= 8 else "Good" if score >= 6 else "Stretch"


def family_weights(job, extra_text=""):
    title = job["title"]
    full = f"{title} {job['category']} {job['description']} {extra_text}"
    weights = {}
    for fam, pattern in FAMILIES.items():
        if re.search(pattern, title, re.I):
            weights[fam] = 2
        elif re.search(pattern, full, re.I):
            weights[fam] = 1
        else:
            weights[fam] = 0
    return weights, full.lower()


# ---------------------------------------------------------------- local AI (Ollama)
def ollama_post(path, payload, timeout=600):
    req = urllib.request.Request(
        OLLAMA_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def ollama_ready():
    """True when Ollama is running and the chat model is installed."""
    try:
        tags = json.loads(fetch(OLLAMA_URL + "/api/tags", timeout=5).decode("utf-8", "ignore"))
    except Exception:
        print("Ollama is not running, so the AI step is off. Using keyword matching only.", file=sys.stderr)
        return False
    names = [m.get("name", "") for m in tags.get("models", [])]
    if any(n == CHAT_MODEL or n.split(":")[0] == CHAT_MODEL for n in names):
        return True
    print(f"Chat model missing. Run: ollama pull {CHAT_MODEL}", file=sys.stderr)
    return False


def resume_summary(resume):
    lines = [f"Education: {resume['education']['degree']}, {resume['education']['date']}. {resume['education']['extra']}"]
    for key in ("experience", "projects", "activities"):
        for it in resume[key]:
            lines.append(f"{it['org']} ({it['role']}): " + " ".join(b["text"] for b in it["bullets"]))
    lines.extend(f"{g['label']}: {', '.join(g['items'])}" for g in resume["skills"])
    return "\n".join(lines)


def judge(summary, job):
    """Ask the local model how well the student fits one posting. Returns a dict or None."""
    thin = len(job["description"]) < 400
    posting = (
        f"Only the title is available: {job['title']} at {job['company']}. Category: {job['category']}."
        if thin
        else f"{job['title']} at {job['company']}\n{job['description'][:3500]}"
    )
    prompt = (
        "You rate how well a student fits one internship. Use only the facts given. Never invent facts.\n"
        "Return JSON only, in this shape: "
        '{"score": 0 to 10, "dealbreakers": ["short phrase"], "reason": "one short sentence"}\n'
        "Score 8 to 10 means the skills match closely. Score 5 to 7 means a partial match. Below 5 means a weak match.\n"
        "Dealbreakers are hard requirements the student fails: a PhD or Master's degree required, "
        "US citizenship or a security clearance required, or dates that do not fit a bachelor's student "
        "who graduates in December 2027. Use an empty list when there are none.\n\n"
        f"STUDENT\n{summary}\n\nPOSTING\n{posting}\n"
    )
    if "qwen3" in CHAT_MODEL:
        prompt += "\n/no_think"
    try:
        data = ollama_post(
            "/api/chat",
            {
                "model": CHAT_MODEL,
                "stream": False,
                "format": "json",
                "think": False,
                "options": {"temperature": 0, "num_ctx": 4096},
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        text = re.sub(r"(?s)<think>.*?</think>", "", data["message"]["content"])
        match = re.search(r"\{.*\}", text, re.S)
        obj = json.loads(match.group(0))
        score = max(0, min(10, int(round(float(obj.get("score", 0))))))
        dealbreakers = [str(d)[:80] for d in (obj.get("dealbreakers") or []) if d][:3]
        return {"score": score, "dealbreakers": dealbreakers, "reason": str(obj.get("reason", ""))[:220], "thin": thin}
    except Exception as exc:
        print(f"AI rating failed for {job['company']}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- linkedin
def top_family(weights):
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    return ranked[0][0] if ranked and ranked[0][1] else "ml"


def linkedin_links(company, fam):
    q = urllib.parse.quote
    role_kw = {"ml": "machine learning engineer", "nlp": "AI engineer", "data": "data scientist",
               "swe": "software engineer", "infra": "ML infrastructure engineer"}[fam]
    base = "https://www.linkedin.com/search/results/people/?keywords="
    return [
        f"   LinkedIn, alumni: {base}{q(company + ' ' + SCHOOL)}",
        f"   LinkedIn, people on the team: {base}{q(company + ' ' + role_kw)}",
        f"   LinkedIn, university recruiters: {base}{q(company + ' university recruiter')}",
    ]


# ---------------------------------------------------------------- small companies
YC_URLS = [
    "https://raw.githubusercontent.com/yc-oss/api/gh-pages/companies/hiring.json",
    "https://yc-oss.github.io/api/companies/hiring.json",
]
SMALL_MIN, SMALL_MAX = 20, 250
SWEET_LOW, SWEET_HIGH = 30, 120  # big enough to be stable, small enough that founders answer email
AI_FIELDS = re.compile(
    r"machine learning|\bai\b|artificial intelligence|\bllm|generative|\bnlp\b|computer vision|"
    r"data engineering|analytics|data infrastructure|\bmlops|developer tools|data",
    re.I,
)


def load_small_companies():
    data = None
    for url in YC_URLS:
        try:
            data = fetch_json(url)
            break
        except Exception as exc:
            print(f"Could not load {url}: {exc}", file=sys.stderr)
    if data is None:
        return []
    out = []
    for c in data:
        size = c.get("team_size") or 0
        if c.get("status") != "Active" or not c.get("isHiring") or c.get("nonprofit"):
            continue
        if not SMALL_MIN <= size <= SMALL_MAX:
            continue
        locations = [c.get("all_locations") or ""]
        where = place_score(locations)
        if where is None and "Remote" in (c.get("regions") or []):
            where = 1
        if where is None:
            continue
        field_text = " ".join([c.get("one_liner") or "", " ".join(c.get("tags") or []), " ".join(c.get("industries") or [])])
        if not AI_FIELDS.search(field_text):
            continue
        score = where
        if re.search(r"machine learning|\bai\b|artificial intelligence|generative|\bllm", field_text, re.I):
            score += 3
        else:
            score += 1
        if SWEET_LOW <= size <= SWEET_HIGH:
            score += 2
        if (c.get("launched_at") or 0) > time.time() - 6 * 365 * 86400:
            score += 1
        out.append(
            {
                "id": f"yc-{c.get('slug')}",
                "name": c.get("name", ""),
                "one_liner": (c.get("one_liner") or "").rstrip("."),
                "size": size,
                "location": c.get("all_locations", ""),
                "batch": c.get("batch", ""),
                "website": c.get("website", ""),
                "yc_url": c.get("url", ""),
                "score": score,
            }
        )
    out.sort(key=lambda c: (-c["score"], abs(c["size"] - 60)))
    return out


EMAIL_TEMPLATE = [
    "Email template for a CEO or founder (edit the brackets, keep it short):",
    "",
    "   Subject: [Your school] [your major] student, summer 2027 internship at [Company]?",
    "",
    "   Hi [First name],",
    "",
    "   I'm a [your school] [your major] student. I saw [Company] is building [what they do, in your own words].",
    "   [One concrete result from your resume, with a number.] Right now I'm",
    "   [what you are building].",
    "",
    "   Could I send you my resume and ask about a summer 2027 internship?",
    "",
    "   Thanks,",
    "   [Your Name]",
    "",
    "How to find the CEO's email: open the YC page listed for each company to see the founders' names. Then check the company",
    "website, the founder's personal site, X, or GitHub for a public email. Hunter.io shows a company's email",
    "pattern for free. Send from your school email address. Follow up once after 5 to 7 days.",
]


# ---------------------------------------------------------------- main
def ckey(j):
    """Same company + title = same posting, whichever source it came from."""
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    return "ck:" + norm(j["company"]) + "|" + norm(j["title"])


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"seen": []}


def prune_old(keep_days):
    """Delete output folders (named YYYY-MM-DD) older than keep_days, and shrink a big run.log."""
    removed = 0
    if OUT_DIR.exists():
        limit = date.today().toordinal() - keep_days
        for d in OUT_DIR.iterdir():
            try:
                if d.is_dir() and date.fromisoformat(d.name).toordinal() < limit:
                    shutil.rmtree(d)
                    removed += 1
            except ValueError:
                continue
    log = BASE / "run.log"
    if log.exists() and log.stat().st_size > 500_000:
        log.write_text("")
    return removed


def main():
    ap = argparse.ArgumentParser(description="Find internships and small companies to email.")
    ap.add_argument("--include-seen", action="store_true", help="also show items from earlier runs")
    ap.add_argument("--days", type=int, default=MAX_AGE_DAYS, help="only postings updated in the last N days")
    ap.add_argument("--no-ai", action="store_true", help="skip the local AI step and use keywords only")
    ap.add_argument("--keep-days", type=int, default=KEEP_DAYS, help="delete reports older than N days")
    args = ap.parse_args()

    resume = json.loads(RESUME_FILE.read_text(encoding="utf-8"))
    state = load_state()
    seen = set(state["seen"])
    cutoff = time.time() - args.days * 86400
    chat_ok = False if args.no_ai else ollama_ready()

    jobs = load_simplify() + load_vanshb03() + load_boards()
    counts = {}
    for j in jobs:
        counts[j["source"]] = counts.get(j["source"], 0) + 1
    print("Sources:", ", ".join(f"{k} {v}" for k, v in counts.items()), flush=True)
    rated = []
    for j in jobs:
        if j["updated"] < cutoff:
            continue
        if not args.include_seen and (j["id"] in seen or ckey(j) in seen):
            continue
        s = rate(j)
        if s is not None:
            j["kw"] = s
            j["ai"] = None
            rated.append(j)
    rated.sort(key=lambda j: (-j["kw"], -j["updated"]))
    # The same posting often appears in more than one source. Keep one copy (prefer direct company links).
    uniq = {}
    for j in sorted(rated, key=lambda j: (j["source"] in ("Simplify", "vanshb03 list"), -j["kw"], -j["updated"])):
        uniq.setdefault(ckey(j), j)
    rated = sorted(uniq.values(), key=lambda j: (-j["kw"], -j["updated"]))

    if chat_ok:
        summary = resume_summary(resume)
        for j in rated[:LLM_CANDIDATES]:
            print(f"Reading {j['company']}, {j['title']}...", flush=True)
            if len(j["description"]) < 400:
                j["description"] = page_text(j["url"])
            j["ai"] = judge(summary, j)

    for j in rated:
        ai = j["ai"]
        if ai:
            j["final"] = j["kw"] + ai["score"] * 2 - (10 if ai["dealbreakers"] else 0)
            if ai["dealbreakers"]:
                j["label"] = "Stretch"
            else:
                j["label"] = "Strong" if ai["score"] >= 7 else "Good" if ai["score"] >= 5 else "Stretch"
        else:
            j["final"] = j["kw"]
            j["label"] = fit_label(j["kw"])
            if chat_ok and j["label"] == "Strong":
                j["label"] = "Good"
    rated.sort(key=lambda j: (-j["final"], -j["updated"]))
    top = rated[:TOP_N_REPORT]
    for j in top:
        j["url"] = resolve_url(j["url"])

    small = [c for c in load_small_companies() if args.include_seen or c["id"] not in seen]
    small = small[:MAX_SMALL_COMPANIES]

    today = date.today().isoformat()
    run_dir = OUT_DIR / today
    run_dir.mkdir(parents=True, exist_ok=True)

    report = [
        f"Internship report for {today}",
        f"Open postings checked: {len(jobs)}. New matches: {len(rated)}.",
        "Sources: " + ", ".join(f"{k} {v}" for k, v in counts.items()),
        f"AI: {CHAT_MODEL} reads postings. It runs on this computer." if chat_ok else "AI: off. Keyword matching only.",
        "",
        "PART 1. INTERNSHIP POSTINGS",
        "",
    ]
    if not top:
        report.append("No new matches today.")
        report.append("")
    for n, j in enumerate(top, 1):
        weights, _ = family_weights(j)
        when = datetime.fromtimestamp(j["updated"], tz=timezone.utc).strftime("%Y-%m-%d")
        report.append(f"{n}. {j['company']}, {j['title']} ({j['label']})")
        report.append(f"   Location: {'; '.join(j['locations']) or 'not listed'}")
        report.append(f"   Updated: {when}")
        report.append(f"   Source: {j['source']}")
        if j["ai"]:
            report.append(f"   Why: {j['ai']['reason']} (AI score {j['ai']['score']} of 10)")
            if j["ai"]["dealbreakers"]:
                report.append(f"   Watch out: {'; '.join(j['ai']['dealbreakers'])}")
            if j["ai"]["thin"]:
                report.append("   Note: the posting page could not be read, so this rating comes from the title only.")
        if j["sponsorship"] and j["sponsorship"] != "Other":
            report.append(f"   Work authorization note: {j['sponsorship']}")
        report.append(f"   Job link: {j['url']}")
        report.extend(linkedin_links(j["company"], top_family(weights)))
        report.append("")

    report.append("PART 2. SMALL AND MID-SIZE COMPANIES TO EMAIL")
    report.append("These companies are hiring now and have 20 to 250 people. Teams of 30 to 120 rank first. They are stable, and founders still read their own email.")
    report.append("")
    if not small:
        report.append("No new companies today.")
        report.append("")
    q = urllib.parse.quote
    base = "https://www.linkedin.com/search/results/people/?keywords="
    for n, c in enumerate(small, 1):
        report.append(f"{n}. {c['name']}: {c['one_liner']}")
        report.append(f"   Team size: {c['size']}. Location: {c['location']}. YC batch: {c['batch']}")
        report.append(f"   Website: {c['website']}")
        report.append(f"   Jobs and founders (YC page): {c['yc_url']}")
        report.append(f"   LinkedIn, CEO or founder: {base}{q(c['name'] + ' CEO founder')}")
        report.append("")
    if small:
        report.extend(EMAIL_TEMPLATE)
        report.append("")

    (run_dir / "report.txt").write_text("\n".join(report), encoding="utf-8")
    state["seen"] = sorted(seen | {j["id"] for j in top} | {ckey(j) for j in top} | {c["id"] for c in small})
    STATE_FILE.write_text(json.dumps(state, indent=1))
    print(f"Done. Report: {run_dir / 'report.txt'}")
    print(f"Postings shown: {len(top)}. Small companies shown: {len(small)}.")
    removed = prune_old(args.keep_days)
    if removed:
        print(f"Deleted {removed} old report folder(s) older than {args.keep_days} days.")


if __name__ == "__main__":
    main()
