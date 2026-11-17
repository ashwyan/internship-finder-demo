#!/bin/bash
# Mac side: pulls reports from the server every 30 minutes and shows a macOS notification.
# Usage:  REMOTE=myserver bash install_mac_pull.sh      (REMOTE = ssh host alias of your server)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"   # this script and pull_reports.sh live together in deploy/mac
REMOTE="${REMOTE:-myserver}"
LABEL="com.example.internshippull"; PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOT
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$HERE/pull_reports.sh</string></array>
  <key>EnvironmentVariables</key><dict><key>REMOTE</key><string>$REMOTE</string></dict>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><true/>
</dict></plist>
EOT
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Reports will appear in ~/internship-finder-reports/reports. Log: ~/internship-finder-reports/pull.log"
