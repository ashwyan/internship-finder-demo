#!/bin/bash
# Linux server side: installs the daily timer (10:17) and the weekly link check. Run from the folder that holds internship_finder.py.
# Put the folder at ~/internship-finder first (the systemd units expect that path).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$HERE" = "$HOME/internship-finder" ] || { echo "Move this folder to ~/internship-finder first."; exit 1; }
[ -f "$HERE/master_resume.json" ] || { echo "Copy master_resume.example.json to master_resume.json and fill in your own details first."; exit 1; }
chmod +x "$HERE"/*.sh
mkdir -p "$HOME/.config/systemd/user"
cp "$HERE"/internship-*.service "$HERE"/internship-*.timer "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now internship-finder.timer internship-recheck.timer
sudo loginctl enable-linger "$USER" 2>/dev/null || loginctl enable-linger "$USER" || true
systemctl --user list-timers --no-pager | grep internship
