#!/usr/bin/env bash
# After touching the compiler or a backend: drop the build cache (it does not follow compiler
# changes), rebuild and check that what is committed matches. Commit build/compiled/ if it changed.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf build/cache
uv run mapper build
uv run mapper check
git status --short build/
