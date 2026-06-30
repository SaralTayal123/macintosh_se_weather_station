#!/usr/bin/env bash
#
# provision-pi.sh — set up a Raspberry Pi (Raspberry Pi OS / Debian) to run macproxy
# with the se-weather (wx) extension as an always-on systemd service.
#
# Usage (on the Pi):
#   git clone <your se-weather repo>      # or copy this repo onto the Pi
#   cd se-weather
#   ./deploy/provision-pi.sh
#
# It is idempotent — re-run it any time to update deps or re-apply the service.
# Run it as your normal login user (NOT root); it uses sudo only where needed.
#
# Override defaults via env vars, e.g.:  PORT=5001 MACPROXY_REPO=... ./deploy/provision-pi.sh
set -euo pipefail

# --- resolve paths from this script's location -------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEWEATHER_DIR="$(dirname "$SCRIPT_DIR")"          # the se-weather repo (contains wx/)
BASE_DIR="$(dirname "$SEWEATHER_DIR")"            # parent dir; macproxy goes alongside
MACPROXY_DIR="${MACPROXY_DIR:-$BASE_DIR/macproxy_classic}"
MACPROXY_REPO="${MACPROXY_REPO:-https://github.com/rdmark/macproxy_classic.git}"
PORT="${PORT:-5001}"
SERVICE="macproxy-wx"
RUN_USER="$(id -un)"

if [ "$RUN_USER" = "root" ]; then
  echo "Please run as your normal login user (not root); sudo is used where needed." >&2
  exit 1
fi

echo ">> se-weather  : $SEWEATHER_DIR"
echo ">> macproxy    : $MACPROXY_DIR"
echo ">> service user: $RUN_USER   port: $PORT"
echo

# --- 1. system packages ------------------------------------------------------
echo ">> [1/6] Installing system packages..."
sudo apt-get update -qq
# python + venv, plus Pillow's runtime libs (freetype is required for TrueType text).
sudo apt-get install -y -qq git python3 python3-venv python3-pip \
  libjpeg-dev zlib1g-dev libfreetype6-dev

# --- 2. clone/update macproxy ------------------------------------------------
echo ">> [2/6] Fetching macproxy_classic..."
if [ -d "$MACPROXY_DIR/.git" ]; then
  git -C "$MACPROXY_DIR" pull --ff-only || echo "   (skip pull; local changes present)"
else
  git clone --depth 1 "$MACPROXY_REPO" "$MACPROXY_DIR"
fi

# --- 3. symlink the wx extension ---------------------------------------------
echo ">> [3/6] Linking wx extension..."
ln -sfn "$SEWEATHER_DIR/wx" "$MACPROXY_DIR/extensions/wx"

# --- 4. enable "wx" in macproxy config.py (idempotent) -----------------------
echo ">> [4/6] Enabling wx in config.py..."
python3 - "$MACPROXY_DIR/config.py" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path).read()
if re.search(r'["\']wx["\']', src):
    print("   wx already enabled")
else:
    new = re.sub(r'(ENABLED_EXTENSIONS\s*=\s*\[)', r'\1\n    "wx",', src, count=1)
    if new == src:
        sys.exit("   ERROR: could not find ENABLED_EXTENSIONS in config.py")
    open(path, "w").write(new)
    print('   added "wx" to ENABLED_EXTENSIONS')
PY

# --- 5. venv + dependencies --------------------------------------------------
echo ">> [5/6] Setting up Python venv + dependencies (this can take a few min)..."
cd "$MACPROXY_DIR"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip wheel
venv/bin/pip install --quiet -r requirements.txt
[ -f extensions/wx/requirements.txt ] && venv/bin/pip install --quiet -r extensions/wx/requirements.txt
# sanity-check the renderer imports (catches missing Pillow/freetype early)
venv/bin/python -c "import sys; sys.path.insert(0,'extensions/wx'); import render; render.comp_graph(render.DEMO); print('   renderer OK')"

# --- 6. install + start the systemd service ----------------------------------
echo ">> [6/6] Installing systemd service ($SERVICE)..."
sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<UNIT
[Unit]
Description=Macproxy (se-weather) for Macintosh SE
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$MACPROXY_DIR
ExecStart=$MACPROXY_DIR/venv/bin/python -u proxy.py --port $PORT
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE.service"

echo
echo ">> Done. Service '$SERVICE' is enabled (starts on boot, restarts on crash)."
echo "   Status : sudo systemctl status $SERVICE"
echo "   Logs   : journalctl -u $SERVICE -f"
echo "   Test   : curl -x http://localhost:$PORT http://wx.com/ | head"
echo
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ">> Point the SE's MacWeb proxy at this Pi:  Host ${IP:-<pi-ip>}   Port $PORT"
echo "   (Give the Pi a static/reserved IP so the address never changes.)"
