#!/bin/bash
# Runs on a Mac every 30 minutes (launchd). Pulls reports from the server and shows a notification.
# If the server cannot be reached, it logs it, warns once per day, and tries again next time.
REMOTE="${REMOTE:-myserver}"            # ssh host alias of the server (see ~/.ssh/config)
REMOTE_DIR="${REMOTE_DIR:-internship-finder}"
DIR="${DIR:-$HOME/internship-finder-reports}"; DEST="$DIR/reports"; LOG="$DIR/pull.log"; ST="$DIR/.pull_state"
mkdir -p "$DEST" "$ST"
TODAY=$(date +%F); NOW=$(date +%H%M)
log(){ echo "$(date '+%F %T') $*" >> "$LOG"; [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 300000 ] && tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; }
notify(){ /usr/bin/osascript - "$1" "$2" <<'AS'
on run argv
  display notification (item 2 of argv) with title (item 1 of argv)
end run
AS
}
once(){ [ -e "$ST/$1" ] && return 1; touch "$ST/$1"; return 0; }   # true only the first time

SSH="ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3"
if ! $SSH "$REMOTE" true 2>/dev/null; then
  log "server unreachable (is the VPN on? is the server on?)"
  if [ "$NOW" -ge 1130 ] && [ ! -s "$DEST/$TODAY/STATUS.txt" ] && once "unreach-$TODAY"; then
    notify "Internship finder: server unreachable" "Cannot fetch today's report. Check the VPN and the server. I will keep retrying."
  fi
  exit 0
fi

if ! rsync -az --timeout=60 -e "$SSH" "$REMOTE":"$REMOTE_DIR"/output/ "$DEST/" 2>>"$LOG"; then
  log "rsync failed"
  once "rsyncfail-$TODAY" && notify "Internship finder: could not copy reports" "The server answered but the copy failed. See $LOG"
  exit 0
fi
log "pulled ok"

# Notify once for the newest report not yet announced; older ones are just marked as seen.
newest=""
for d in $(ls -1 "$DEST" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort); do
  [ -s "$DEST/$d/STATUS.txt" ] || continue
  [ -e "$ST/notified-$d" ] && continue
  touch "$ST/notified-$d"; newest="$d"
done
for d in $(ls -1 "$DEST" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'); do
  if [ -s "$DEST/$d/recheck.txt" ] && [ ! -e "$ST/recheck-$d" ]; then
    touch "$ST/recheck-$d"; notify "Internship links: weekly check" "$(sed -n 1p "$DEST/$d/recheck.txt")"
  fi
done
if [ -n "$newest" ]; then
  status=$(sed -n 1p "$DEST/$newest/STATUS.txt"); notes=$(sed -n 2p "$DEST/$newest/STATUS.txt")
  top=$(grep -E '^[0-9]+\. ' "$DEST/$newest/report.txt" 2>/dev/null | head -3 | sed -E 's/^[0-9]+\. //' | tr '\n' '|' | sed 's/|$//; s/|/ ; /g')
  case "$status" in
    FAILED) notify "Internship finder FAILED ($newest)" "$notes" ;;
    *) if grep -q "No new matches today" "$DEST/$newest/report.txt" 2>/dev/null
       then notify "Internships $newest: no new matches" "Nothing new since yesterday. $notes"
       else notify "Internships $newest: $notes" "${top:-open the report}  (reports/$newest/report.txt)"; fi ;;
  esac
  log "notified $newest: $status $notes"
elif [ "$NOW" -ge 1400 ] && [ ! -s "$DEST/$TODAY/STATUS.txt" ] && once "missing-$TODAY"; then
  notify "Internship finder: no report today" "The server is reachable but no report exists for $TODAY. Check run.log on the server."
fi
