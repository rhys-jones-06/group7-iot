#!/usr/bin/env bash
# LockIn Pi — One-command setup
# Run once via SSH:
#   curl -sL https://raw.githubusercontent.com/c24057633/group-7-iot/appstart/pi/setup.sh | sudo bash
#
# Expects /boot/lockin.conf to already be present (downloaded from dashboard Settings page).

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
    echo "  3. Copy the file to /boot/ on this Pi"
    echo "  4. Re-run this script"
    exit 1
fi
echo "✓ lockin.conf found"

# ── System dependencies ───────────────────────────────────────────────────────
echo "Installing system packages..."
apt-get update -qq
apt-get install -y -qq git python3-pip python3-venv libcap-dev

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

# ── Python virtualenv ─────────────────────────────────────────────────────────
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet requests
# Uncomment to install camera/CV deps when detection is implemented:
# "$INSTALL_DIR/.venv/bin/pip" install --quiet opencv-python-headless
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
echo "  LockIn will start automatically on every boot."
echo ""
echo "  Check status:  sudo systemctl status $SERVICE"
echo "  View logs:     sudo journalctl -u $SERVICE -f"
echo "==============================="
