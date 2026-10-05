#!/usr/bin/env bash
# Format and lint only the Python files that changed (staged, unstaged or new), never the whole
# repo: `ruff format .` rewrites the code blocks in docs/ARCHITECTURE.md.
set -euo pipefail
cd "$(dirname "$0")/.."
files=$( (git diff --name-only HEAD; git ls-files --others --exclude-standard) | grep '\.py$' | sort -u || true)
[ -z "$files" ] && { echo "no Python file changed"; exit 0; }
# shellcheck disable=SC2086
uv run ruff format $files
# shellcheck disable=SC2086
uv run ruff check $files
