#!/usr/bin/env bash
set -euo pipefail

PREFIX="${HOME}/.local"
VENV_PATH=""
UNINSTALL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        --venv) VENV_PATH="$2"; shift 2 ;;
        --uninstall) UNINSTALL=1; shift ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# The NetPulse core package lives at network-monitor/app, one level up
# from this script's directory (desktop/). This is also where
# requirements.txt lives. Using $SCRIPT_DIR/.. instead of $SCRIPT_DIR/../..
# because app/ is inside network-monitor/, not at the top of the git
# repository (which is one further level up and contains only .git/,
# network-monitor/, and the repo's own files).
NETPULSE_ROOT="$( cd -- "$SCRIPT_DIR/.." &> /dev/null && pwd )"

APP_INSTALL_DIR="${PREFIX}/share/netpulse"
APP_INSTALL_DESKTOP="${APP_INSTALL_DIR}/desktop"
APP_INSTALL_APP="${APP_INSTALL_DIR}/app"
BIN_DIR="${PREFIX}/bin"
LAUNCHER_PATH="${BIN_DIR}/netpulse"
DESKTOP_DIR="${PREFIX}/share/applications"
DESKTOP_PATH="${DESKTOP_DIR}/netpulse.desktop"
ICON_DIR="${PREFIX}/share/icons/hicolor/256x256/apps"
ICON_PATH="${ICON_DIR}/netpulse.png"

if [[ "$UNINSTALL" == "1" ]]; then
    echo "Uninstalling NetPulse from ${PREFIX} ..."
    rm -f "$LAUNCHER_PATH" "$DESKTOP_PATH" "$ICON_PATH"
    rm -rf "$APP_INSTALL_DIR"
    echo "Done."
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi
    exit 0
fi

if [[ ! -d "$NETPULSE_ROOT/app" ]]; then
    echo "Cannot find the NetPulse 'app' package." >&2
    echo "Expected: $NETPULSE_ROOT/app" >&2
    echo "This script lives at $SCRIPT_DIR" >&2
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
    echo "Cannot find main.py next to install.sh." >&2
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/resources/netpulse.png" ]]; then
    echo "Missing icon: $SCRIPT_DIR/resources/netpulse.png" >&2
    echo "Run: python3 make_icon.py" >&2
    exit 1
fi

if [[ -z "$VENV_PATH" ]]; then
    VENV_PATH="${APP_INSTALL_DIR}/.venv"
fi

echo "NetPulse installer"
echo "  source      : $SCRIPT_DIR"
echo "  app source  : $NETPULSE_ROOT/app"
echo "  app install : $APP_INSTALL_DIR"
echo "  launcher    : $LAUNCHER_PATH"
echo "  menu entry  : $DESKTOP_PATH"
echo "  icon        : $ICON_PATH"
echo "  venv        : $VENV_PATH"
echo

echo "Copying application files..."
mkdir -p "$APP_INSTALL_DESKTOP" "$APP_INSTALL_APP"

# Note the .env exclusion. .env holds the user's SMTP credentials and
# must never be copied from a developer's working tree into a fresh
# install; that would ship the developer's password to anyone who
# installs the app. Each user creates their own .env from the
# .env.example template.
rsync -a --delete \
    --exclude 'data/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.venv/' \
    --exclude 'resources/' \
    --exclude '.env' \
    "$SCRIPT_DIR/" "$APP_INSTALL_DESKTOP/"

rsync -a --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$NETPULSE_ROOT/app/" "$APP_INSTALL_APP/"

# Seed the install dir with a .env.example so the user has a template
# to copy from. Never seed it with the developer's .env.
if [[ -f "$SCRIPT_DIR/.env.example" ]]; then
    cp "$SCRIPT_DIR/.env.example" "$APP_INSTALL_DESKTOP/.env.example"
fi

if [[ -d "$SCRIPT_DIR/data" ]]; then
    if [[ ! -d "$APP_INSTALL_DESKTOP/data" ]]; then
        echo "Copying initial data/ ..."
        rsync -a "$SCRIPT_DIR/data/" "$APP_INSTALL_DESKTOP/data/"
    fi
fi
mkdir -p "$APP_INSTALL_DESKTOP/data"

if [[ ! -x "$VENV_PATH/bin/python3" ]]; then
    echo "Creating virtual environment at $VENV_PATH ..."
    python3 -m venv "$VENV_PATH"
fi

echo "Installing Python dependencies..."
"$VENV_PATH/bin/pip" install --upgrade pip >/dev/null
if [[ -f "$NETPULSE_ROOT/requirements.txt" ]]; then
    "$VENV_PATH/bin/pip" install -r "$NETPULSE_ROOT/requirements.txt"
fi

# PySide6-Essentials, not the full PySide6 metapackage. The metapackage
# additionally pulls PySide6-Addons (~60 MB), PySide6-WebEngine (~60 MB),
# and PySide6-Pdf (~5 MB). None of those are used by the desktop app,
# which needs only QtCore, QtGui, and QtWidgets — all of which live in
# Essentials. This drops the download from ~200 MB to ~85 MB.
"$VENV_PATH/bin/pip" install PySide6-Essentials

echo "Installing launcher at $LAUNCHER_PATH ..."
mkdir -p "$BIN_DIR"
sed -e "s|__INSTALL_DIR__|$APP_INSTALL_DESKTOP|g" \
    -e "s|__VENV_DIR__|$VENV_PATH|g" \
    "$SCRIPT_DIR/resources/netpulse" > "$LAUNCHER_PATH"
chmod +x "$LAUNCHER_PATH"

echo "Installing icon at $ICON_PATH ..."
mkdir -p "$ICON_DIR"
cp "$SCRIPT_DIR/resources/netpulse.png" "$ICON_PATH"

echo "Installing menu entry at $DESKTOP_PATH ..."
mkdir -p "$DESKTOP_DIR"
cp "$SCRIPT_DIR/resources/netpulse.desktop" "$DESKTOP_PATH"

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true
fi

echo
echo "Installed."
echo
echo "Launch NetPulse from:"
echo "  - Your applications menu (search 'NetPulse')"
echo "  - Or run:  netpulse"
echo
if [[ ":"$PATH":" != *":${BIN_DIR}:"* ]]; then
    echo "Note: ${BIN_DIR} is not on your PATH."
    echo "Add this to your shell config."
    echo
    echo "  bash/zsh — add to ~/.bashrc or ~/.zshrc:"
    echo "      export PATH=\"${BIN_DIR}:\$PATH\""
    echo
    echo "  fish — run once, then restart the shell:"
    echo "      fish_add_path ${BIN_DIR}"
    echo
fi