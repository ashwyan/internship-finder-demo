#!/bin/bash
# Linux server: installs the daily timer (10:17) and the weekly link check.
# Put the whole repo at ~/internship-finder first (the systemd units expect that path), then run:  bash deploy/server/install_server.sh
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[ "$ROOT" = "$HOME/internship-finder" ] || { echo "Move this repo to ~/internship-finder first (it is at $ROOT)."; exit 1; }
[ -f "$ROOT/master_resume.json" ] || { echo "Copy master_resume.example.json to master_resume.json and fill in your own details first."; exit 1; }
chmod +x "$ROOT"/src/*.sh "$ROOT"/deploy/*/*.sh
mkdir -p "$HOME/.config/systemd/user"
cp "$ROOT"/deploy/server/internship-*.service "$ROOT"/deploy/server/internship-*.timer "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now internship-finder.timer internship-recheck.timer
sudo loginctl enable-linger "$USER" 2>/dev/null || loginctl enable-linger "$USER" || true
systemctl --user list-timers --no-pager | grep internship
