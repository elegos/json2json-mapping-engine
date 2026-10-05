#!/usr/bin/env bash
# Everything CI runs offline, in its order: ruff, basedpyright (without the local, git-ignored
# pyrightconfig.json, which would hide the real errors), track-1 tests, and the UI tests/types.
#   dev_scripts/check.sh            all of it
#   dev_scripts/check.sh --no-ui    skip the frontend
# Format only the files you touched: `uv run ruff format <files>` (never the whole repo).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== ruff"; uv run ruff check .
echo "== basedpyright"
cfg=pyrightconfig.json
[ -f "$cfg" ] && mv "$cfg" "$cfg.aside"
trap '[ -f "$cfg.aside" ] && mv "$cfg.aside" "$cfg"' EXIT
uv run basedpyright
echo "== pytest track1"; uv run pytest tests/track1 -q
if [ "${1:-}" != "--no-ui" ]; then
  echo "== ui"; (cd desktop/ui && npx tsc --noEmit && npx vitest run)
fi
