#!/usr/bin/env bash
# The headless-browser checks of the desktop UI (desktop/ui/shots/*-check.mjs), which drive the
# real `mapper` through the bridge. Name some (`wizard golden-run`) or run all.
set -euo pipefail
cd "$(dirname "$0")/../desktop/ui"
names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  for f in shots/*-check.mjs; do b=$(basename "$f" -check.mjs); names+=("$b"); done
fi
for n in "${names[@]}"; do
  echo "== $n"; node "shots/$n-check.mjs"
done
