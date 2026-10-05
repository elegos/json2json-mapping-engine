#!/usr/bin/env bash
# Regenerate the guide's screenshots (all, or the named ones).
set -euo pipefail
cd "$(dirname "$0")/../desktop/ui"
node shots/run.mjs "$@"
