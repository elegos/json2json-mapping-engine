"""`mapper serve` — a long-lived worker for the desktop tool.

Reads one JSON request per line on stdin, answers one JSON line on stdout. It exists
so that per-edit operations (Target / Source normalisation) cost a message, not a
Python start-up. Requests: `{"id", "op", ...}`; answers `{"id", "ok", ...}`.

Ops: `ping`; `complete` (`tree`, `project`, `stem`, `path`, `column`, `text`, `cursor`: what can be typed there, see `transpiler/complete.py`); `check` (`tree`, `project`, `stem`); `retarget` (`tree`, `path`, `value`); `set_source` (`tree`, `path`,
`value`); `add_rule` (`tree`, `parent`, `index`, `kind`); `delete_rule` (`tree`, `path`); `proposal` (`tree`, `path`: the auto code, the override), `take_over` / `accept_proposal` / `keep_override` (`tree`, `path`), `set_override` (`tree`, `path`, `code`), see `transpiler/review.py`; `check` also answers `review` (overrides whose auto code moved); `schemas_status` (`tree`, `project`, `stem`: the input and output schema of a mapping, `ok` / `missing` / `invalid`), `schema_import` (`project`, `stem`, `kind`, `source`: copy a schema into the project as the mapping's own); `mapping_create` (`project`, `name`, `golden`?, `golden_to`?), `mapping_golden` (`project`, `name`: the cases already in `tests/golden/<name>/`), `mapping_removal` / `mapping_delete` (`project`, `name`, `golden`?: what deleting takes, then does it; with `golden` the golden cases too), `mapping_rename` (`project`, `name`, `new`, `file_id`?), see `cli/mappings.py`; `golden_cases` (`project`, `mapping`), `golden_import` (`project`, `mapping`, `name`, `input`, `expected`?, `errors`?: copy the files in under the standard names), `golden_rename` (`name`, `new`), `golden_delete` (`name`), `golden_read` (`name`: the text of each file of a case), `golden_write` (`name`, `role` input / expected / errors, `text`: checked, `null` removes the file), `golden_create` (`name`, `text`?: a case with only an input), see `cli/golden.py`; `golden_run` (`mapping`, `names`?: run the cases on the Python backend, pass / fail, output, rule errors, diff), `input_run` (`mapping`, `input`: the same on any JSON file, nothing written), `golden_record` (`name`: take the output now as the expected one), see `cli/golden_run.py`; `scaffold` (`tree`, `project`, `stem`, `apply`: the empty rules the output schema adds, see `transpiler/scaffold.py`; with `apply` also the new `tree`); `config_read` (`project`), `config_check` (`values`), `config_write` (`project`, `values`): `mapper.toml`, see `cli/project_config.py`; `vcs_ensure_driver` (`project`: have the clone merge mappings and functions at the rule level; quiet) / `vcs_state` / `vcs_summary` / `vcs_commit` (`notes`, `wip`: check, build and one commit of the sources and the generated files) / `vcs_pull` (rebase) / `vcs_push` (both take `credentials`: `username`, `password`, for a remote that asks; the answer to a failure that credentials could cure has `auth_required`) / `vcs_conflicts` / `vcs_resolve` (`file`, `choices`: path -> `mine` | `remote`) / `vcs_init` (`project`: put the project under git: `main`, a `.gitignore`, the merge driver; nothing committed) / `vcs_abort` (`project`: git mode, see `cli/vcs.py`); `artifacts_state` (`project`: `committed` / `ignored` / `unknown` and the tracked files of `build/compiled`), `artifacts_ignore` / `artifacts_track` (`project`: stop or resume committing them, see `cli/artifacts_mode.py`; the git index change is staged, not committed); `shared_seen` (`project`, `file`: the file on disk is the version this user has seen) / `shared_prepare` (`project`, `file`, `text` or `tree`: before a save in a synced folder, `same` / `merged` with the `text` and `tree` to save / `conflict` with `items`) / `shared_settle` (the same, plus `choices`) / `shared_scan` (`project`: `changed` files and conflict `copies`) / `shared_copy_merge` / `shared_copy_settle` / `shared_copy_discard` (`project`, `copy`), see `cli/shared.py`; `synced_remove_git` (`project`: delete the `.git` of a repository in a synced folder, the files stay), `synced_status` (`project`: `synced` the sync provider or null, `git` a repository in a synced folder, see `cli/synced.py`); `engine_status` (`project`: `status` current / upgrade / older / unversioned, the project's engine version and the tool's), `engine_upgrade` (`project`: write the tool's version into `mapper.toml`, forward only; answers the status from before), see `cli/engine_version.py`; `functions` (`project`?: the built-in and project functions, see `cli/functions.py`); `project_backends` (the backends and their options, as `config_read`'s `schema`), `project_create` (`project`, `target`, `options`?: a new `mapper.toml` and the project's folders), see `cli/project_create.py`; `fn_files` (`project`), `fn_read` / `fn_write` / `fn_create` / `fn_delete` (`project`, `file`, `text`?: the project's `fn/*.fn`; a write that does not parse is refused), `fn_check` (`project`, `file`, `text`: issues), `fn_rename_plan` / `fn_rename` (`project`, `name`, `new`: where a project function is used, and the rename of its `def` and its calls in the other functions and the mappings), `fn_add` (`project`, `file`, `name`: a stub function at the end of a file), `fn_override` (`project`, `name`: copy a built-in into `fn/builtin_overrides.fn`), `fn_call` (`project`, `name`, `args`, `text`?: a test call on Python), see `cli/fn_files.py`; `lookups_shared` (`project`: the project-wide lookups and the mappings that read each), `lookup_save` (`project`, `label`, `entries`, `type`?, `description`?, `create`?: answers the mappings whose rules went back to review), `lookup_delete` (`project`, `label`: refused while a mapping reads it), `lookup_share` (`project`, `stem`, `label`: move a mapping's lookup into the project), `lookup_unshare` (`project`, `label`: give each mapping that reads it a copy), see `transpiler/shared_lookups.py`. `tree` is the file as `mapper fn read` prints it; the answer carries the new
`tree`, or `error`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

import yaml

from cli import (
    artifacts_mode,
    engine_version,
    fn_files,
    fn_rename,
    functions,
    golden,
    golden_run,
    mappings,
    project_config,
    project_create,
    synced,
    vcs,
)
from cli import shared as shared_folder
from cli.build_dir import BUILD_ENV
from cli.config import MapperConfigError
from compiler.function_registry import all_functions
from compiler.schema_files import import_schema, schema_status
from transpiler import review as rv
from transpiler import shared_lookups as shared
from transpiler.check import check_functional, schemas_for
from transpiler.complete import complete
from transpiler.edit import add_rule, delete_rule, retarget, set_source
from transpiler.model import FnYamlError, functional_from_dict, functional_to_dict, parse_functional
from transpiler.scaffold import scaffold_rules
from transpiler.serialize import functional_to_yaml

_REVIEW_OPS = {
    "proposal": None,
    "set_override": None,
    "take_over": rv.take_over,
    "accept_proposal": rv.accept_proposal,
    "keep_override": rv.keep_override,
}


def _fn_call(request: dict[str, Any]) -> dict[str, Any]:
    return fn_files.call_function(
        Path(request["project"]), request["name"], request.get("args", []), request.get("text")
    )


_FN_OPS: dict[str, Any] = {
    "fn_files": lambda r: {"ok": True, "files": fn_files.list_files(Path(r["project"]))},
    "fn_read": lambda r: {"ok": True, "text": fn_files.read_file(Path(r["project"]), r["file"])},
    "fn_check": lambda r: {
        "ok": True,
        "issues": fn_files.check_text(Path(r["project"]), r["file"], r["text"]),
    },
    "fn_write": lambda r: (
        fn_files.write_file(Path(r["project"]), r["file"], r["text"]) or {"ok": True}
    ),
    "fn_create": lambda r: (
        fn_files.create_file(Path(r["project"]), r["file"], r.get("text")) or {"ok": True}
    ),
    "fn_add": lambda r: (
        fn_files.add_function(Path(r["project"]), r["file"], r["name"]) or {"ok": True}
    ),
    "fn_rename_plan": lambda r: {
        "ok": True,
        **fn_rename.rename_plan(Path(r["project"]), r["name"]),
    },
    "fn_rename": lambda r: {
        "ok": True,
        **fn_rename.rename_function(Path(r["project"]), r["name"], r["new"]),
    },
    "fn_delete": lambda r: {
        "ok": True,
        "functions": fn_files.delete_file(Path(r["project"]), r["file"]),
    },
    "fn_override": lambda r: {
        "ok": True,
        **fn_files.override_builtin(Path(r["project"]), r["name"]),
    },
    "fn_call": _fn_call,
}


def _text_of(request: dict[str, Any], rel: str) -> str:
    """What the tool is saving: the file's text, or (a mapping) its Rule Tree as JSON."""
    if rel.endswith(".fn.yaml") and "tree" in request:
        return functional_to_yaml(functional_from_dict(request["tree"]))
    return request["text"]


def _with_tree(rel: str, answer: dict[str, Any]) -> dict[str, Any]:
    """A merged mapping also comes as the Rule Tree the grid shows."""
    if answer.get("text") is not None and rel.endswith(".fn.yaml"):
        raw = yaml.safe_load(answer["text"]) or {}
        stem = rel.rsplit("/", 1)[-1].removesuffix(".fn.yaml")
        answer = {**answer, "tree": functional_to_dict(parse_functional(raw, default_id=stem))}
    return answer


_SHARED_OPS: dict[str, Any] = {
    "shared_seen": lambda r: shared_folder.seen(Path(r["project"]), r["file"]) or {},
    "shared_prepare": lambda r: _with_tree(
        r["file"], shared_folder.prepare(Path(r["project"]), r["file"], _text_of(r, r["file"]))
    ),
    "shared_settle": lambda r: _with_tree(
        r["file"],
        shared_folder.settle(Path(r["project"]), r["file"], _text_of(r, r["file"]), r["choices"]),
    ),
    "shared_scan": lambda r: shared_folder.scan(Path(r["project"])),
    "shared_copy_merge": lambda r: _with_tree(
        shared_folder.original_of(Path(r["project"]), r["copy"]) or "",
        shared_folder.merge_copy(Path(r["project"]), r["copy"]),
    ),
    "shared_copy_settle": lambda r: _with_tree(
        shared_folder.original_of(Path(r["project"]), r["copy"]) or "",
        shared_folder.settle_copy(Path(r["project"]), r["copy"], r["choices"]),
    ),
    "shared_copy_discard": lambda r: (
        shared_folder.discard_copy(Path(r["project"]), r["copy"]) or {}
    ),
}


def handle(request: dict[str, Any]) -> dict[str, Any]:
    """One request. `build_dir` and `allow_synced` (the tool adds them for a project in a synced
    folder, from this user's choice) apply to this request only: the worker serves every project."""
    moved = {
        BUILD_ENV: request.get("build_dir"),
        shared_folder.BASE_ENV: request.get("base_dir"),
        synced.ALLOW_ENV: "1" if request.get("allow_synced") else None,
    }
    moved = {name: str(value) for name, value in moved.items() if value}
    if not moved:
        return _handle(request)
    before = {name: os.environ.get(name) for name in moved}
    os.environ.update(moved)
    try:
        return _handle(request)
    finally:
        for name, value in before.items():
            if value is None:
                del os.environ[name]
            else:
                os.environ[name] = value


def _handle(request: dict[str, Any]) -> dict[str, Any]:
    op = request.get("op")
    if op == "ping":
        return {"ok": True}
    if op == "check":
        file = functional_from_dict(request["tree"])
        inp, out = schemas_for(Path(request["project"]), request["stem"], file.schemas)
        issues = check_functional(file, inp, out, all_functions(Path(request["project"])))
        try:
            flags = [r.to_json() for r in rv.review(file)]
        except FnYamlError:
            flags = []  # a rule that cannot be transpiled is the check's business
        return {"ok": True, "diagnostics": [i.to_json() for i in issues], "review": flags}
    if op == "complete":
        file = functional_from_dict(request["tree"])
        inp, out = schemas_for(Path(request["project"]), request["stem"], file.schemas)
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
    if op == "schemas_status":
        refs = functional_from_dict(request["tree"]).schemas
        project = Path(request["project"])
        return {
            "ok": True,
            "input": schema_status(project, request["stem"], "input", refs.input),
            "output": schema_status(project, request["stem"], "output", refs.output),
        }
    if op == "schema_import":
        project = Path(request["project"])
        import_schema(project, request["stem"], request["kind"], Path(request["source"]))
        return {"ok": True, **schema_status(project, request["stem"], request["kind"])}
    if op == "mapping_create":
        file = mappings.create_mapping(
            Path(request["project"]),
            request["name"],
            request.get("golden"),
            request.get("golden_to"),
        )
        return {"ok": True, "file": file}
    if op == "mapping_golden":
        return {"ok": True, **mappings.golden_state(Path(request["project"]), request["name"])}
    if op == "mapping_removal":
        return {
            "ok": True,
            "files": mappings.removal_plan(Path(request["project"]), request["name"]),
        }
    if op == "mapping_delete":
        return {
            "ok": True,
            "files": mappings.delete_mapping(
                Path(request["project"]), request["name"], bool(request.get("golden"))
            ),
        }
    if op == "mapping_rename":
        done = mappings.rename_mapping(
            Path(request["project"]), request["name"], request["new"], request.get("file_id")
        )
        return {"ok": True, **done}
    if op == "golden_cases":
        return {
            "ok": True,
            "cases": golden.list_cases(Path(request["project"]), request["mapping"]),
        }
    if op == "golden_import":

        def maybe(key: str) -> Path | None:
            return Path(request[key]) if request.get(key) else None

        files = golden.import_case(
            Path(request["project"]),
            request["mapping"],
            request["name"],
            Path(request["input"]),
            maybe("expected"),
            maybe("errors"),
        )
        return {"ok": True, "files": files}
    if op == "golden_read":
        return {
            "ok": True,
            "files": golden.read_case(
                Path(request["project"]), request["mapping"], request["name"]
            ),
        }
    if op == "golden_write":
        golden.write_case_file(
            Path(request["project"]),
            request["mapping"],
            request["name"],
            request["role"],
            request.get("text"),
        )
        return {"ok": True}
    if op == "golden_create":
        golden.create_case(
            Path(request["project"]), request["mapping"], request["name"], request.get("text", "{}")
        )
        return {"ok": True}
    if op == "golden_run":
        names = request.get("names")
        return {
            "ok": True,
            "results": golden_run.run_cases(
                Path(request["project"]), request["mapping"], names if names else None
            ),
        }
    if op == "input_run":
        return {
            "ok": True,
            "result": golden_run.run_input(
                Path(request["project"]), request["mapping"], Path(request["input"])
            ),
        }
    if op == "golden_record":
        return {
            "ok": True,
            **golden_run.record_case(Path(request["project"]), request["mapping"], request["name"]),
        }
    if op == "golden_rename":
        golden.rename_case(
            Path(request["project"]), request["mapping"], request["name"], request["new"]
        )
        return {"ok": True}
    if op == "golden_delete":
        files = golden.delete_case(Path(request["project"]), request["mapping"], request["name"])
        return {"ok": True, "files": files}
    if op == "scaffold":
        file = functional_from_dict(request["tree"])
        _, out = schemas_for(Path(request["project"]), request["stem"], file.schemas)
        if out is None:
            return {"ok": False, "error": "the mapping has no output schema (or it cannot be read)"}
        found = scaffold_rules(file, out)
        answer: dict[str, Any] = {"ok": True, "added": found.added, "skipped": found.skipped}
        if request.get("apply"):
            answer["tree"] = functional_to_dict(found.file)
        return answer
    if op == "functions":
        project = request.get("project")
        return {
            "ok": True,
            "functions": functions.function_list(Path(project) if project else None),
        }
    if op in _FN_OPS:
        return _FN_OPS[op](request)
    if op == "lookups_shared":
        return {"ok": True, "lookups": shared.describe(Path(request["project"]))}
    if op == "lookup_save":
        marked = shared.save(
            Path(request["project"]),
            request["label"],
            request["entries"],
            request.get("type"),
            request.get("description"),
            bool(request.get("create")),
        )
        return {"ok": True, "marked": marked}
    if op == "lookup_delete":
        shared.delete(Path(request["project"]), request["label"])
        return {"ok": True}
    if op == "lookup_share":
        clashing = shared.share(Path(request["project"]), request["stem"], request["label"])
        return {"ok": True, "clashing": clashing}
    if op == "lookup_unshare":
        return {
            "ok": True,
            "changed": shared.unshare(Path(request["project"]), request["label"]),
        }
    if op == "project_backends":
        return {"ok": True, **project_config.describe()}
    if op == "project_create":
        project_create.create_project(
            Path(request["project"]), request["target"], request.get("options")
        )
        return {"ok": True}
    if op == "vcs_ensure_driver":
        return {"ok": True, **vcs.ensure_driver(Path(request["project"]))}
    if op == "vcs_state":
        return {"ok": True, **vcs.state(Path(request["project"]))}
    if op == "vcs_summary":
        return {"ok": True, "lines": vcs.summary(Path(request["project"]))}
    if op == "vcs_commit":
        return vcs.commit(
            Path(request["project"]), request.get("notes", ""), wip=bool(request.get("wip"))
        )
    if op == "vcs_pull":
        return vcs.pull(Path(request["project"]), request.get("credentials"))
    if op == "vcs_push":
        return vcs.push(Path(request["project"]), request.get("credentials"))
    if op == "vcs_conflicts":
        return {"ok": True, "files": vcs.conflicts(Path(request["project"]))}
    if op == "vcs_resolve":
        return vcs.resolve(Path(request["project"]), request["file"], request.get("choices"))
    if op == "vcs_init":
        return vcs.init_repo(Path(request["project"]))
    if op == "vcs_abort":
        return vcs.abort(Path(request["project"]))
    if op == "artifacts_state":
        return {"ok": True, **artifacts_mode.state(Path(request["project"])).to_json()}
    if op in ("artifacts_ignore", "artifacts_track"):
        act = artifacts_mode.ignore if op == "artifacts_ignore" else artifacts_mode.track
        before = act(Path(request["project"]))
        return {"ok": True, "before": before.to_json()}
    if op in _SHARED_OPS:
        return {"ok": True, **_SHARED_OPS[op](request)}
    if op == "synced_remove_git":
        return {"ok": True, **synced.remove_git(Path(request["project"]))}
    if op == "synced_status":
        return {"ok": True, **synced.status(Path(request["project"]))}
    if op == "engine_status":
        return {"ok": True, **engine_version.status(Path(request["project"])).to_json()}
    if op == "engine_upgrade":
        before = engine_version.upgrade(Path(request["project"]))
        return {"ok": True, **before.to_json()}
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
        except (
            FnYamlError,
            MapperConfigError,
            vcs.VcsError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            answer = {"ok": False, "error": f"{exc}"}
            if getattr(exc, "auth", False):  # more credentials could cure it: the tool asks
                answer["auth_required"] = True
        answer["id"] = request_id
        stdout.write(json.dumps(answer, ensure_ascii=False) + "\n")
        stdout.flush()
