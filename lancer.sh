#!/usr/bin/env bash
# Lanceur simple de Tontolo (chat en terminal, cœur Python).
set -euo pipefail
cd "$(dirname "$0")/core"

if [ ! -x ".venv/bin/tontolo" ]; then
    echo "Première installation, un instant..."
    python3 -m venv .venv
    .venv/bin/pip install -q -e ".[dev,linux]"
fi

TONTOLO=".venv/bin/tontolo"

echo "=== Tontolo ==="
echo "Tapez votre message puis Entrée. Ctrl+C pour quitter."
echo

conv_args=()
while true; do
    read -r -e -p "Vous > " msg
    [ -z "$msg" ] && continue

    errfile=$(mktemp)
    printf "Tontolo > "
    "$TONTOLO" chat "${conv_args[@]}" "$msg" 2> "$errfile"
    echo

    conv_id=$(grep -oP '\[conversation \K[^]]+' "$errfile" || true)
    if [ -n "$conv_id" ]; then
        conv_args=(--conversation "$conv_id")
    fi
    rm -f "$errfile"
done
