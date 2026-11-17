#!/bin/bash
# Run on the Linux server:  bash fix_sleep_server.sh     (asks for the sudo password once)
# Never sleep while plugged in, and closing the lid does nothing while plugged in. Battery behavior is unchanged.
set -e
sudo mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\nIdleAction=ignore\n' | sudo tee /etc/systemd/logind.conf.d/10-internship-no-sleep.conf >/dev/null
sudo systemctl kill -s HUP systemd-logind
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' || true
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 0 || true
echo "--- now:"; grep -rh "^Handle\|^IdleAction" /etc/systemd/logind.conf.d/
gsettings get org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type || true
