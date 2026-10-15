"""Stage artifacts of the transpiler (docs/ARCHITECTURE.md, §Transpiler pipeline).

Four stages: `load` (rule tree, JSON), `build` (`.map.py` before loop fusion),
`fuse` (`.map.py` after loop fusion), `emit` (the final `.map.py`). Each can be
written to `<out_dir>/<N>-<name>.<ext>`; a run up to stage N leaves exactly
stages 1..N on disk (later ones are removed, so the directory never mixes
generations). With `cached`, stage N starts from the artifact of stage N-1 when
it exists, instead of re-running from `.fn.yaml`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from compiler.schema_generator import SchemaTypes
from transpiler.model import (
    FnYamlError,
    FunctionalFile,
    functional_from_dict,
    functional_to_dict,
    load_functional_file,
)
from transpiler.transpile import TranspileOptions, build_stage, emit_stage, fuse_stage

STAGES = ("load", "build", "fuse", "emit")
_EXT = {"load": "json", "build": "map.py", "fuse": "map.py", "emit": "map.py"}


def parse_stage(value: str) -> int:
    """`1`..`4` or an alias (`load`, `build`, `fuse`, `emit`) -> 1..4."""
    if value in STAGES:
        return STAGES.index(value) + 1
    if value.isdigit() and 1 <= int(value) <= len(STAGES):
        return int(value)
    raise FnYamlError(f"unknown stage {value!r}: use 1-{len(STAGES)} or {', '.join(STAGES)}")


def artifact(out_dir: Path, stage: int) -> Path:
    return out_dir / f"{stage}-{STAGES[stage - 1]}.{_EXT[STAGES[stage - 1]]}"


def run_stages(
    path: Path,
    options: TranspileOptions,
    upto: int,
    out_dir: Path | None,
    input_schema: SchemaTypes | None = None,
    cached: bool = False,
    warnings: list[str] | None = None,
    log: list[str] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> str:
    """Run stages up to `upto` and return the last stage's text. `out_dir=None`
    writes nothing (and `cached` is then meaningless). `log` receives one line
    when `cached` had to fall back to a full run."""
    start = 1
    if cached and out_dir is not None and upto > 1 and artifact(out_dir, upto - 1).is_file():
        start = upto
    if log is not None and cached and upto > 1 and start == 1:
        log.append(f"cached: no stage {upto - 1} artifact in {out_dir} — running from stage 1")

    def read(stage: int) -> str:
        assert out_dir is not None
        return artifact(out_dir, stage).read_text()

    def write(stage: int, text: str) -> None:
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            artifact(out_dir, stage).write_text(text)

    tree: FunctionalFile | None = None
    text = ""
    for stage in range(start, upto + 1):
        if stage == 1:
            tree = load_functional_file(path)
            text = json.dumps(functional_to_dict(tree), indent=2, ensure_ascii=False, default=str)
        elif stage == 2:
            if tree is None:
                tree = functional_from_dict(json.loads(read(1)))
            text = build_stage(tree, options, input_schema, warnings, output_schema)
        else:
            src = text if stage > start else read(stage - 1)
            text = fuse_stage(src, options) if stage == 3 else emit_stage(src, options, path.name)
        write(stage, text)

    if out_dir is not None:
        for later in range(upto + 1, len(STAGES) + 1):
            artifact(out_dir, later).unlink(missing_ok=True)
    return text
