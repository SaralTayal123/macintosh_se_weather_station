#!/usr/bin/env bash
#
# provision-statusui.sh — install the touchscreen status panel on a Raspberry Pi
# running Raspberry Pi OS **Desktop**. Run AFTER deploy/provision-pi.sh.
#
#   ./deploy/provision-statusui.sh
#
# It: installs pygame (system package), grants a no-password sudo rule so the
# "Restart Proxy" button works, and adds a desktop autostart entry so the panel
# launches fullscreen when the Pi logs into the desktop. Idempotent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEWEATHER_DIR="$(dirname "$SCRIPT_DIR")"
APP="$SEWEATHER_DIR/statusui/status_app.py"
RUN_USER="$(id -un)"
SERVICE="${WX_SERVICE:-macproxy-wx}"

[ "$RUN_USER" = "root" ] && { echo "Run as your normal desktop user, not root." >&2; exit 1; }
[ -f "$APP" ] || { echo "Cannot find $APP" >&2; exit 1; }

echo ">> [1/3] Installing pygame (system package)..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pygame

# The proxy writes the status file (last_seen etc.), but systemd loaded wx.py once
# at start — restart it so a freshly-pulled wx.py actually starts writing the file.
echo ">> Restarting the proxy so it picks up the latest wx.py..."
sudo systemctl restart "$SERVICE" 2>/dev/null \
  && echo "   $SERVICE restarted" \
  || echo "   (could not restart $SERVICE — run: sudo systemctl restart $SERVICE)"

echo ">> [2/3] Granting no-password sudo for the Restart Proxy button..."
SUDOERS=/etc/sudoers.d/macproxy-statusui
sudo tee "$SUDOERS" >/dev/null <<SUDO
# Allow $RUN_USER to (re)start the weather proxy from the touchscreen panel.
$RUN_USER ALL=(root) NOPASSWD: /bin/systemctl restart $SERVICE, /usr/bin/systemctl restart $SERVICE
SUDO
sudo chmod 0440 "$SUDOERS"
sudo visudo -cf "$SUDOERS" >/dev/null && echo "   sudoers rule OK"

echo ">> [3/3] Installing desktop autostart entry..."
WRAPPER="$SEWEATHER_DIR/statusui/run-panel.sh"
chmod +x "$WRAPPER"
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
# The wrapper restarts the app on crash and logs to ~/se-weather-status.log.
cat > "$AUTOSTART_DIR/se-weather-status.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=SE Weather Status
Comment=Touchscreen status panel for the Macintosh SE weather proxy
Exec=$WRAPPER
X-GNOME-Autostart-enabled=true
Terminal=false
DESKTOP

# If we're being run from within the desktop session, start it now too, so you
# see it immediately (not only after the next login).
if [ -n "${WAYLAND_DISPLAY:-}" ] || [ -n "${DISPLAY:-}" ]; then
  pkill -f "statusui/status_app.py" 2>/dev/null || true
  nohup "$WRAPPER" >/dev/null 2>&1 &
  echo ">> Launched the panel now (you're in a desktop session)."
else
  echo ">> No desktop session detected here (are you on SSH?)."
  echo "   It will start on the next desktop login/reboot."
fi

echo
echo ">> Done."
echo "   Autostarts on desktop login; restarts on crash; logs to ~/se-weather-status.log"
echo "   Try now on the touchscreen's own terminal:  $WRAPPER"
echo "   Or the app directly (to see errors live):    python3 $APP"
echo "   Tail the log:                                tail -f ~/se-weather-status.log"
