#!/usr/bin/env bash
# QR code de l'écran « À propos » : page de la DERNIÈRE version (téléchargements), donc à
# générer une seule fois. Relu par zbarimg : jamais un code faux.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="https://github.com/raantss18/tontolo/releases/latest"
OUT="$ROOT/app/assets/qr/download.png"
qrencode -o "$OUT" -s 8 -m 2 -l M "$URL"
test "$(zbarimg -q --raw "$OUT")" = "$URL" || { echo "QR illisible" >&2; exit 1; }
echo "$OUT"
