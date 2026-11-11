#!/usr/bin/env bash
# Builds out/obs-game-capture.zip for Decky → Developer → "Install plugin from ZIP".
set -euo pipefail
cd "$(dirname "$0")/.."
pnpm run build
rm -rf out && mkdir -p out/obs-game-capture/py_modules
cp -r dist main.py plugin.json package.json LICENSE README.md out/obs-game-capture/
cp -r py_modules/obscapture out/obs-game-capture/py_modules/
rm -f out/obs-game-capture/dist/*.map
find out -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr obs-game-capture.zip obs-game-capture)
echo "out/obs-game-capture.zip"
