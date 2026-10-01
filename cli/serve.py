"""`mapper serve` — a long-lived worker for the desktop tool.

Reads one JSON request per line on stdin, answers one JSON line on stdout. It exists
so that per-edit operations (Target / Source normalisation) cost a message, not a
Python start-up. Requests: `{"id", "op", ...}`; answers `{"id", "ok", ...}`.

Ops: `ping`; `complete` (`tree`, `project`, `stem`, `path`, `column`, `text`, `cursor`: what can be typed there, see `transpiler/complete.py`); `check` (`tree`, `project`, `stem`); `retarget` (`tree`, `path`, `value`); `set_source` (`tree`, `path`,
`value`); `add_rule` (`tree`, `parent`, `index`, `kind`); `delete_rule` (`tree`, `path`); `proposal` (`tree`, `path`: the auto code, the override), `take_over` / `accept_proposal` / `keep_override` (`tree`, `path`), `set_override` (`tree`, `path`, `code`), see `transpiler/review.py`; `check` also answers `review` (overrides whose auto code moved, validated rules whose functions changed signature); `config_read` (`project`), `config_check` (`values`), `config_write` (`project`, `values`): `mapper.toml`, see `cli/project_config.py`. `tree` is the file as `mapper fn read` prints it; the answer carries the new
`tree`, or `error`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from cli import project_config
from cli.config import MapperConfigError
from compiler.function_registry import all_functions
from transpiler import review as rv
from transpiler.check import check_functional, schemas_for
from transpiler.complete import complete
from transpiler.edit import add_rule, delete_rule, retarget, set_source
from transpiler.model import FnYamlError, functional_from_dict, functional_to_dict

_REVIEW_OPS = {
    "proposal": None,
    "set_override": None,
    "take_over": rv.take_over,
    "accept_proposal": rv.accept_proposal,
    "keep_override": rv.keep_override,
}


def handle(request: dict[str, Any]) -> dict[str, Any]:
    op = request.get("op")
    if op == "ping":
        return {"ok": True}
    if op == "check":
        file = functional_from_dict(request["tree"])
        inp, out = schemas_for(Path(request["project"]), request["stem"])
        issues = check_functional(file, inp, out, all_functions(Path(request["project"])))
        try:
            flags = [r.to_json() for r in rv.review(file, all_functions(Path(request["project"])))]
        except FnYamlError:
            flags = []  # a rule that cannot be transpiled is the check's business
        return {"ok": True, "diagnostics": [i.to_json() for i in issues], "review": flags}
    if op == "complete":
        file = functional_from_dict(request["tree"])
        inp, out = schemas_for(Path(request["project"]), request["stem"])
        found = complete(
            file,
            request["path"],
            request["column"],
            request["text"],
            request["cursor"],
            inp,
            out,
            all_functions(Path(request["project"])),
        )
        return {"ok": True, **found.to_json()}
    if op in ("retarget", "set_source"):
        file = functional_from_dict(request["tree"])
        change = retarget if op == "retarget" else set_source
        return {
            "ok": True,
            "tree": functional_to_dict(change(file, request["path"], request["value"])),
        }
    if op in _REVIEW_OPS:
        file = functional_from_dict(request["tree"])
        if op == "proposal":
            return {"ok": True, **rv.proposal_view(file, request["path"])}
        if op == "set_override":
            file = rv.set_override(file, request["path"], request["code"])
        else:
            file = _REVIEW_OPS[op](file, request["path"])
        return {"ok": True, "tree": functional_to_dict(file)}
    if op == "config_read":
        return {"ok": True, **project_config.read(Path(request["project"]))}
    if op == "config_check":
        return {"ok": True, "issues": project_config.check(request["values"])}
    if op == "config_write":
        project_config.write(Path(request["project"]), request["values"])
        return {"ok": True}
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
        except (FnYamlError, MapperConfigError, ValueError, KeyError, TypeError) as exc:
            answer = {"ok": False, "error": f"{exc}"}
        answer["id"] = request_id
        stdout.write(json.dumps(answer, ensure_ascii=False) + "\n")
        stdout.flush()
