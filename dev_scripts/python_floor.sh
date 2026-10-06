#!/usr/bin/env bash
# The golden cases run by the generated modules on other Pythons than the engine's: the first one
# the backend supports (compiler/backends/python/runtime.py, MIN_PYTHON) and the others given.
#   dev_scripts/python_floor.sh                  3.10, 3.11, 3.14t
#   dev_scripts/python_floor.sh 3.10 3.13        only these (uv fetches an interpreter it does not have)
set -euo pipefail
cd "$(dirname "$0")/.."

versions=("$@")
[ ${#versions[@]} -gt 0 ] || versions=(3.10 3.11 3.14t)

out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

# the modules of every golden mapping, with process-parallel loops (the most that is generated)
uv run python - "$out" <<'PY'
import sys
from pathlib import Path

from compiler.backends.python.backend import PythonBackend
from compiler.pipeline import compile_unit

names = sorted(p.name for p in Path("tests/golden").iterdir() if (Path("mappings") / f"{p.name}.map.py").exists())
backend = PythonBackend({"parallel": "process"})
units = [compile_unit(Path(f"mappings/{n}.map.py").read_text(), n, backend) for n in names]
for name, text in backend.assemble(units).items():
    (Path(sys.argv[1]) / name).write_text(text)
PY

cat > "$out/run_cases.py" <<'PY'
import glob, importlib, json, os, sys

# the guard matters: with process-parallel loops the workers import this script again
if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])
    bad = 0
    for inp in sorted(glob.glob("tests/golden/*/*.input.json")):
        mapping = inp.split("/")[2]
        case = os.path.basename(inp)[: -len(".input.json")]
        module = importlib.import_module(f"map_{mapping}")
        output, _errors = getattr(module, f"map_{mapping}_safe")(json.load(open(inp)))
        if output != json.load(open(inp.replace(".input.", ".expected."))):
            bad += 1
            print("DIFFERS:", mapping, case)
    gil = "" if getattr(sys, "_is_gil_enabled", lambda: True)() else " (free-threaded)"
    print(sys.version.split()[0] + gil, "-", "all cases agree" if not bad else f"{bad} differ")
    sys.exit(1 if bad else 0)
PY

status=0
for v in "${versions[@]}"; do
  uv run --no-project --python "$v" python "$out/run_cases.py" "$out" || status=1
done
exit $status
