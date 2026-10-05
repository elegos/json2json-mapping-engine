#!/usr/bin/env bash
# The golden cases on a real Oracle (CI's integration job), about 2 minutes, needs docker.
# `build/cache` does not follow compiler changes, so it is cleared first; commit the regenerated
# build/compiled/ if it changed.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf build/cache
uv run mapper build
uv run mapper test --integration
