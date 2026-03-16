#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo " VsdxViewer -- PyInstaller build"
echo "========================================"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found."
    exit 1
fi

# Install dependencies
echo ""
echo "[1/3] Installing dependencies..."
python3 -m pip install --upgrade pip --quiet
python3 -m pip install -r requirements.txt --quiet
python3 -m pip install pyinstaller --quiet

# Clean
echo ""
echo "[2/3] Cleaning previous build..."
rm -rf build dist

# Build
echo ""
echo "[3/3] Building executable..."
python3 -m PyInstaller VsdxViewer.spec

echo ""
echo "========================================"
echo " Done!  Executable: dist/VsdxViewer/VsdxViewer"
echo " Distribute the entire dist/VsdxViewer/ folder."
echo "========================================"
