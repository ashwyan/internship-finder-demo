#!/usr/bin/env python3
"""Emails today's summary to yourself via Gmail. Skipped silently if ~/.config/internship/gmail is missing.
That file: line 1 = your Gmail address, line 2 = a Google App Password (myaccount.google.com/apppasswords).
Never fails the daily run: exit 0 sent, 2 skipped, 1 error."""
import smtplib, ssl, sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent if HERE.name == "src" else HERE   # data (resume, state, output) lives at the repo root
cred = Path.home() / ".config/internship/gmail"
if not cred.exists():
    print("email: no credentials file, skipped"); sys.exit(2)
addr, pw = (l.strip() for l in cred.read_text().splitlines()[:2])
out = BASE / "output" / date.today().isoformat()
def read(n): f = out / n; return f.read_text() if f.exists() else ""
st = read("STATUS.txt").splitlines() or ["FAILED", "no status file"]
report, gem = read("report.txt"), read("gemini_search.txt")
tops = [l for l in report.splitlines() if l[:2].strip(". ").isdigit() or (l[:1].isdigit() and ". " in l[:4])][:8]
body = [f"Status: {st[0]}", st[1] if len(st) > 1 else "", ""]
body += (["Top matches:"] + tops) if tops else ["No new matches in the main report today."]
if gem:
    body += ["", "Gemini search:"] + [l for l in gem.splitlines() if l[:1].isdigit() or l.startswith("===")][:12]
body += ["", f"Full files are on the server: output/{date.today().isoformat()}/ (also copied to your Mac reports folder)."]
m = EmailMessage(); m["From"] = addr; m["To"] = addr
m["Subject"] = f"Internships {date.today()}: {st[0]} - {st[1] if len(st) > 1 else ''}"[:150]
m.set_content("\n".join(body))
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
        s.login(addr, pw); s.send_message(m)
    print("email: sent"); sys.exit(0)
except Exception as e:
    print(f"email: failed: {type(e).__name__}"); sys.exit(1)
