# Internship Finder (demo)

A free, self-hosted tool that finds ML / AI / data internships every morning, rates them against your resume with a **local** AI model, and sends you a notification. No paid API required.

> This is a demo version. The resume in `master_resume.example.json` is fake. Put your own details in `master_resume.json` (it is git-ignored, so it never gets pushed).

## What you get each day

- `output/YYYY-MM-DD/report.txt`
  - **Part 1:** open internships (ML, AI, data science, data engineering), posted in the last 14 days, across the US and remote. Each has the job link and three LinkedIn search links (alumni, people on the team, university recruiters).
  - **Part 2:** up to 8 small and mid-size companies that are hiring (from the free Y Combinator list), with a CEO email template.
- `output/YYYY-MM-DD/gemini_search.txt` *(optional)*: extra postings found by Gemini with Google Search. These are leads only: not rated, links are checked and dead ones dropped.
- `output/YYYY-MM-DD/STATUS.txt`: `OK`, `WARN` or `FAILED`, plus one line of notes.
- A weekly `recheck.txt` listing postings that have closed.
- Postings you have already seen are skipped next time (kept in `state.json`).

**See what it produces:** [`examples/sample_report.txt`](examples/sample_report.txt) (generated from the fake resume, keyword mode).

## How it fits together

```
 Linux server (always on)                         Your Mac
 ┌───────────────────────────────┐   rsync/ssh   ┌──────────────────────────────┐
 │ systemd timer, daily 10:17    │ ────────────► │ launchd, every 30 min        │
 │  internship_finder.py (+Ollama)│               │  pull_reports.sh             │
 │  gemini_search.py  (optional)  │               │  macOS notification          │
 │  notify_email.py   (optional)  │               │  warns once if server is off │
 └───────────────────────────────┘               └──────────────────────────────┘
```

If the server is off or unreachable, the Mac logs it, warns you **once** per day after 11:30, and keeps retrying. When the server is back, missed reports are copied automatically (the timer uses `Persistent=true`, so a missed run still happens).

## Quick start (just try it, any OS with Python 3.8+)

```bash
cp master_resume.example.json master_resume.json   # then edit with your own details
python3 internship_finder.py --no-ai                # keyword matching only, takes seconds
```

Optional local AI: install [Ollama](https://ollama.com), then `ollama pull qwen3:4b` and `ollama pull nomic-embed-text`, and run without `--no-ai`. A full AI run took about 3 minutes on a laptop-class CPU in testing.

Options: `--no-ai`, `--include-seen`, `--days N`, `--keep-days N`.

## Run it every day on a Linux server

1. Copy this folder to `~/internship-finder` on the server and create your `master_resume.json`.
2. Make sure Ollama starts at boot (`systemctl is-enabled ollama`).
3. `bash install_server.sh` installs a systemd user timer (daily 10:17) and a weekly link check, and enables lingering so it runs without you logged in.
4. Optional: `bash fix_sleep_server.sh` stops a laptop server from sleeping while plugged in.

Check it:

```bash
systemctl --user list-timers internship-finder.timer --no-pager
systemctl --user status internship-finder.service --no-pager | head
tail run.log
systemctl --user start internship-finder.service      # run it now
```

## Get reports and notifications on a Mac

Add the server to `~/.ssh/config` (key-based login, no password), then:

```bash
REMOTE=myserver bash install_mac_pull.sh
tail ~/internship-finder-reports/pull.log
cat ~/internship-finder-reports/reports/$(ls ~/internship-finder-reports/reports | grep -E '^[0-9]{4}' | tail -1)/report.txt
```

## Optional extras

**Gemini job search** (leads only, not rating, your resume is *not* sent). Put a free key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) in `~/.config/internship/gemini_key` (mode 600). It runs after the finder, one Google-Search query per US region. Edit `ROLES`, `TERM`, `REGIONS`, `PREFERRED` at the top of `gemini_search.py`. It skips postings seen on earlier days, dead links, non-intern titles and anything in `applied.txt`.

**Email summary.** Create `~/.config/internship/gmail` with two lines: your Gmail address and a [Google App Password](https://myaccount.google.com/apppasswords). You get one short email per day.

**Applied list.** Add a company name or link per line to `applied.txt`; the Gemini search and the weekly check skip them.

None of the extras can break the main run. A missing key skips the step, and a failure only adds a warning to `STATUS.txt`.

## Change what it searches

Edit the settings at the top of `internship_finder.py`: `TERMS`, `BAY_AREA`, `OTHER_TARGETS` (cities, now the whole US), title keywords, days back, result counts, company size range, and `SCHOOL`.

## Limits

- Small local models make mistakes. Check every posting before you apply.
- Many career pages need JavaScript and can't be read; the report marks those as rated from the title only.
- Gemini search results vary day to day and can be wrong or stale; links are checked, content is not.
- The tool does not find email addresses. It points you to founders so you can find them yourself.

## Privacy

Everything runs on your own machines. Without the optional extras, nothing leaves your network except fetching public job lists. Never commit `master_resume.json` or your key files (they are in `.gitignore`).

## Credits

- Internship listings: the community-maintained [SimplifyJobs Summer 2027 Internships](https://github.com/SimplifyJobs/Summer2027-Internships) list.
- Small-company list: the free [yc-oss API](https://github.com/yc-oss/api) of Y Combinator companies.
- Optional direct company boards: public Greenhouse and Lever job APIs.
- Local AI: [Ollama](https://ollama.com) with `qwen3:4b` and `nomic-embed-text`.

This project is not affiliated with any of them. Please respect their terms and rate limits.

## License

MIT
