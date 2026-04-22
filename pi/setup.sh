#!/usr/bin/env bash
# LockIn Pi — Headless Setup Script
# ============================================================
# BEFORE running this script you need three files on the Pi's
# SD card boot partition (plug it into any PC/Mac first):
#
#   /boot/lockin.conf       — download from dashboard → Settings
#   /boot/ssh               — empty file, enables SSH on first boot
#   /boot/wpa_supplicant.conf — WiFi credentials (see below)
#
# wpa_supplicant.conf template:
#   country=GB
#   ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
#   update_config=1
#   network={
#       ssid="YOUR_WIFI_NAME"
#       psk="YOUR_WIFI_PASSWORD"
#   }
#
# Once the SD card is in and the Pi has booted (give it ~60s),
# find its IP via your router or: ping lockin.local
# Then SSH in and run:
#
#   curl -sL https://raw.githubusercontent.com/c24057633/group-7-iot/appstart/pi/setup.sh | sudo bash
#
# ============================================================

set -euo pipefail

REPO_URL="https://git.cardiff.ac.uk/c24057633/group-7-iot.git"
BRANCH="appstart"
INSTALL_DIR="/opt/lockin"
SERVICE="lockin"
PI_USER="${SUDO_USER:-pi}"

echo "==============================="
echo "  LockIn Pi Setup"
echo "==============================="

# ── Check config file ────────────────────────────────────────────────────────
if [ ! -f /boot/lockin.conf ] && [ ! -f /boot/firmware/lockin.conf ]; then
    echo ""
    echo "ERROR: /boot/lockin.conf not found."
    echo "  1. Go to the LockIn dashboard → Settings"
    echo "  2. Click 'Download lockin.conf'"
    echo "  3. Plug the SD card into your PC and copy the file to /boot/"
    echo "  4. Re-run this script"
    exit 1
fi
echo "✓ lockin.conf found"

# ── System dependencies ───────────────────────────────────────────────────────
echo "Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    git \
    python3-pip \
    python3-venv \
    python3-picamera2 \
    python3-opencv \
    python3-rpi.gpio \
    libcap-dev
echo "✓ System packages installed"

# ── GrovePi ───────────────────────────────────────────────────────────────────
if ! python3 -c "import grovepi" 2>/dev/null; then
    echo "Installing GrovePi library..."
    pip3 install --quiet grovepi 2>/dev/null || \
        pip3 install --quiet "git+https://github.com/DexterInd/GrovePi.git#subdirectory=Software/Python" || \
        echo "Warning: GrovePi install failed — buzzer alerts will be disabled. Install manually if needed."
fi
echo "✓ GrovePi checked"

# ── Clone / update repo ───────────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing installation..."
    git -C "$INSTALL_DIR" fetch origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
else
    echo "Cloning repo..."
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
echo "✓ Code at $INSTALL_DIR"

# ── Python virtualenv (system-site-packages so picamera2/cv2 are available) ──
echo "Setting up Python environment..."
python3 -m venv --system-site-packages "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements-pi.txt"
echo "✓ Python environment ready"

# ── systemd service ───────────────────────────────────────────────────────────
cat > /etc/systemd/system/${SERVICE}.service << EOF
[Unit]
Description=LockIn Focus Monitor
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/pi/main.py
WorkingDirectory=$INSTALL_DIR/pi
Restart=always
RestartSec=15
User=$PI_USER
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"
echo "✓ systemd service '$SERVICE' enabled and started"

echo ""
echo "==============================="
echo "  Setup complete!"
echo "  LockIn starts automatically on every boot."
echo ""
echo "  Check status:  sudo systemctl status $SERVICE"
echo "  View logs:     sudo journalctl -u $SERVICE -f"
echo "==============================="
