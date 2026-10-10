#!/usr/bin/env bash
# Empaquette le cœur Python pour l'application (serious_python).
# Usage : scripts/package_python.sh Android|Linux
set -euo pipefail
PLATFORM="${1:?Android ou Linux}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SERIOUS_PYTHON_VERSION="${SERIOUS_PYTHON_VERSION:-3.14}"
export SERIOUS_PYTHON_SITE_PACKAGES="$ROOT/app/build/site-packages-$PLATFORM"
export SERIOUS_PYTHON_APP="$ROOT/app/build/python-app-$PLATFORM"

# Roue du cœur, construite depuis les sources
rm -rf "$ROOT/core/dist"
(cd "$ROOT/core" && uv build -q --wheel)
WHEEL="$(ls "$ROOT"/core/dist/tontolo-*.whl)"

rm -rf "$SERIOUS_PYTHON_SITE_PACKAGES" "$SERIOUS_PYTHON_APP"
cd "$ROOT/app"
# Android : cœur seul (replis légers intégrés pour la recherche web et MCP,
# ≈ 30 Mo de moins par ABI). Linux : ddgs et SDK MCP officiel (stdio + HTTP).
if [ "$PLATFORM" = "Android" ]; then REQ="tontolo @ file://$WHEEL"
else REQ="tontolo[search,mcp] @ file://$WHEEL"; fi
dart run serious_python:main package python -p "$PLATFORM" -r "$REQ" \
  --cleanup
du -sh "$SERIOUS_PYTHON_SITE_PACKAGES" "$SERIOUS_PYTHON_APP" 2>/dev/null || true
