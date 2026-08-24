#!/usr/bin/env bash
# server_setup.sh - run this ON THE CLOUD SERVER (Ubuntu 22.04/24.04), not locally.
#
# Usage (after you SSH in yourself, e.g. `ssh root@<你的服务器公网IP>`):
#   curl -fsSL <raw-url-or-scp-this-file-over> -o server_setup.sh
#   bash server_setup.sh
#
# What it does:
#   1. installs python3.12, git, tmux
#   2. creates /opt/nfi and clones the upstream strategy repo into nfi_repo/
#   3. builds a venv and installs freqtrade + freqtrade_client (pinned to the
#      same 2026.7 version this project was validated against)
#
# It does NOT copy your local fixes (NostalgiaForInfinityX7Safe.py, the
# local-overrides-*.json configs, X7SafeVariants.py) - those only exist on
# your Windows machine and must be pushed over separately. See DEPLOY.md
# step 3 for the rsync/scp command.

set -euo pipefail

APP_DIR="/opt/nfi"
FREQTRADE_VERSION="2026.7"

echo "[1/4] apt packages"
apt-get update -y
apt-get install -y python3.12 python3.12-venv git tmux ufw

echo "[2/4] clone upstream strategy repo"
mkdir -p "$APP_DIR"
cd "$APP_DIR"
if [ -d nfi_repo/.git ]; then
  git -C nfi_repo pull
else
  git clone https://github.com/iterativv/NostalgiaForInfinity.git nfi_repo
fi

echo "[3/4] venv + freqtrade"
python3.12 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install "freqtrade==$FREQTRADE_VERSION" "freqtrade_client==$FREQTRADE_VERSION"

echo "[4/4] directory layout"
mkdir -p "$APP_DIR/user_data/strategies" "$APP_DIR/configs" "$APP_DIR/user_data/logs"

echo "done. Next: copy user_data/strategies/*.py and configs/*.json from your"
echo "local machine into $APP_DIR (see DEPLOY.md step 3), then run preflight.py"
echo "on the server before starting the bot."
