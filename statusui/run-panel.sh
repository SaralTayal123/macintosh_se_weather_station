#!/usr/bin/env bash
#
# run-panel.sh — launch the touchscreen status panel, restart it if it crashes,
# and log to a file so failures are visible. This is what the desktop autostart
# entry runs (see deploy/provision-statusui.sh). Runs inside the desktop session,
# so it inherits the correct DISPLAY / WAYLAND_DISPLAY automatically.
#
# Log:  ~/se-weather-status.log   (override with WX_UI_LOG)
set -u
cd "$(dirname "$0")"
LOG="${WX_UI_LOG:-$HOME/se-weather-status.log}"
exec >>"$LOG" 2>&1
echo "=== run-panel wrapper started $(date) ==="
while true; do
  echo "--- launching status_app.py $(date) ---"
  python3 status_app.py
  echo "--- status_app.py exited ($?) $(date); restarting in 3s ---"
  sleep 3
done
