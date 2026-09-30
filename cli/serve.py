"""`mapper serve` — a long-lived worker for the desktop tool.

Reads one JSON request per line on stdin, answers one JSON line on stdout. It exists
so that per-edit operations (Target / Source normalisation) cost a message, not a
Python start-up. Requests: `{"id", "op", ...}`; answers `{"id", "ok", ...}`.

Ops: `ping`; `check` (`tree`, `project`, `stem`); `retarget` (`tree`, `path`, `value`); `set_source` (`tree`, `path`,
`value`); `add_rule` (`tree`, `parent`, `index`, `kind`); `delete_rule` (`tree`, `path`). `tree` is the file as `mapper fn read` prints it; the answer carries the new
`tree`, or `error`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from transpiler.check import check_functional, schemas_for
from transpiler.edit import add_rule, delete_rule, retarget, set_source
from transpiler.model import FnYamlError, functional_from_dict, functional_to_dict


def handle(request: dict[str, Any]) -> dict[str, Any]:
    op = request.get("op")
    if op == "ping":
        return {"ok": True}
    if op == "check":
        file = functional_from_dict(request["tree"])
        inp, out = schemas_for(Path(request["project"]), request["stem"])
        issues = check_functional(file, inp, out)
        return {"ok": True, "diagnostics": [i.to_json() for i in issues]}
    if op in ("retarget", "set_source"):
        file = functional_from_dict(request["tree"])
        change = retarget if op == "retarget" else set_source
        return {
            "ok": True,
            "tree": functional_to_dict(change(file, request["path"], request["value"])),
        }
    if op in ("add_rule", "delete_rule"):
        file = functional_from_dict(request["tree"])
        if op == "add_rule":
            file = add_rule(file, request.get("parent"), request.get("index"), request["kind"])
        else:
            file = delete_rule(file, request["path"])
        return {"ok": True, "tree": functional_to_dict(file)}
    return {"ok": False, "error": f"unknown op {op!r}"}


def serve(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    for line in stdin:
        if not line.strip():
            continue
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            answer = handle(request)
        except (FnYamlError, ValueError, KeyError, TypeError) as exc:
            answer = {"ok": False, "error": f"{exc}"}
        answer["id"] = request_id
        stdout.write(json.dumps(answer, ensure_ascii=False) + "\n")
        stdout.flush()
