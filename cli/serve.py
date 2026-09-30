"""`mapper serve` — a long-lived worker for the desktop tool.

Reads one JSON request per line on stdin, answers one JSON line on stdout. It exists
so that per-edit operations (Target / Source normalisation) cost a message, not a
Python start-up. Requests: `{"id", "op", ...}`; answers `{"id", "ok", ...}`.

Ops: `ping`; `retarget` (`tree`, `path`, `value`); `set_source` (`tree`, `path`,
`value`). `tree` is the file as `mapper fn read` prints it; the answer carries the new
`tree`, or `error`.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from transpiler.edit import retarget, set_source
from transpiler.model import FnYamlError, functional_from_dict, functional_to_dict


def handle(request: dict[str, Any]) -> dict[str, Any]:
    op = request.get("op")
    if op == "ping":
        return {"ok": True}
    if op in ("retarget", "set_source"):
        file = functional_from_dict(request["tree"])
        change = retarget if op == "retarget" else set_source
        return {
            "ok": True,
            "tree": functional_to_dict(change(file, request["path"], request["value"])),
        }
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
