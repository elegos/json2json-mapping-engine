#!/usr/bin/env bash
# The git fallback (gitoxide, desktop/gitfallback): builds the helper and runs the offline tests of
# the git side on BOTH backends, the `git` binary and the helper.
#   dev_scripts/gix.sh           build + test
#   dev_scripts/gix.sh --rust    also the Rust tests of the crate
set -euo pipefail
cd "$(dirname "$0")/.."

# the gix cases are the point here: a missing helper is a failure, not a skip
export J2JME_REQUIRE_GIX=1

echo "== build the helper"; (cd desktop/gitfallback && cargo build --locked)
if [ "${1:-}" = "--rust" ]; then
  echo "== cargo test"; (cd desktop/gitfallback && cargo test)
fi
echo "== pytest, both backends"
uv run pytest tests/track1/cli/test_vcs.py tests/track1/cli/test_artifacts_mode.py \
  tests/track1/merge/test_ensure_driver.py tests/track1/cli/test_gitops.py -q
