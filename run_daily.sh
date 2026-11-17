#!/bin/bash
# Daily wrapper for internship_finder.py (runs on the Linux server).
# Writes output/<date>/STATUS.txt. Line 1: OK | WARN | FAILED. Line 2: short notes.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
exec 9>/tmp/internship_finder.lock
if ! flock -n 9; then echo "=== $(date '+%F %T') skipped: a previous run is still running"; exit 0; fi

TODAY=$(date +%F); OUT=output/$TODAY; START=/tmp/.internship_finder_start
echo "=== $(date '+%F %T') run start"; touch "$START"
# make sure Ollama is up (it is enabled at boot; this is a safety net)
if ! curl -s -m 5 http://localhost:11434/api/version >/dev/null; then
  echo "Ollama not responding, trying to start it"; (systemctl --user start ollama 2>/dev/null || nohup ollama serve >/dev/null 2>&1 &); sleep 15
fi
curl -s -m 5 http://localhost:11434/api/version >/dev/null || echo "WARNING: Ollama is not responding; the AI step will be off"

timeout 3h /usr/bin/python3 internship_finder.py "$@"; code=$?
echo "=== $(date '+%F %T') run end, exit code $code"

status=OK; notes=""
add()  { notes="${notes}$1; "; }
warn() { [ "$status" = OK ] && status=WARN; add "$1"; }
fail() { status=FAILED; add "$1"; }
[ $code -eq 124 ] && fail "timed out after 3 hours"
[ $code -ne 0 ] && [ $code -ne 124 ] && fail "script exited with code $code (see run.log on the server)"
{ [ -s "$OUT/report.txt" ] && [ "$OUT/report.txt" -nt "$START" ]; } || fail "no report was created today"
if [ "$status" != FAILED ]; then
  grep -q "^AI: off" "$OUT/report.txt" && warn "AI was off, so ratings use keywords only"
  if grep -q "No new matches today" "$OUT/report.txt"; then add "no new matches today"
  else n=$(grep -oE "New matches: [0-9]+" "$OUT/report.txt" | grep -oE "[0-9]+"); add "${n:-?} new matches"; fi
fi
# Optional Gemini job SEARCH (skipped silently if no key; a failure only adds a warning)
if [ "$status" != FAILED ] && [ -f gemini_search.py ]; then
  timeout 1200 /usr/bin/python3 gemini_search.py; g=$?
  [ $g -eq 0 ] && add "Gemini search: $(cat "$OUT/.gemini_count" 2>/dev/null || echo 0) extra companies"
  [ $g -eq 1 ] && warn "Gemini search failed (main report is still fine)"
fi
mkdir -p "$OUT"
printf '%s\n%s\n' "$status" "${notes%; }" > "$OUT/STATUS.txt"
[ -f notify_email.py ] && timeout 60 /usr/bin/python3 notify_email.py
echo "STATUS: $status - ${notes%; }"
[ "$status" = FAILED ] && exit 1
exit 0
