"""`mapper` — build CLI entry point (see docs/ARCHITECTURE.md, §Build CLI)."""

from __future__ import annotations

import contextlib
import functools
import io
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from cli import engine_version, shared, synced
from cli import functions as functions_catalogue
from cli.build import (
    BuildError,
    assemble,
    backend_for,
    compile_fresh,
    compile_mapping,
    discover_mappings,
    stages_dir,
    transpile_functional,
    write_package,
)
from cli.build_dir import compiled_dir
from cli.config import MapperConfigError, load_config
from cli.manifest import artifacts_ignored, build_manifest, compare, read_manifest
from cli.stubs import generate_stubs
from cli.track1 import run_track1
from cli.track2 import Track2Error, integration_state, run_track2
from compiler.function_registry import all_functions
from transpiler.check import check_functional, schemas_for
from transpiler.model import (
    FnYamlError,
    functional_from_dict,
    functional_to_dict,
    load_functional_file,
)
from transpiler.review import demote_invalid, validation_touched_ids
from transpiler.serialize import apply_decay_tree, write_functional
from transpiler.stages import STAGES, artifact, parse_stage

app = typer.Typer(add_completion=False, no_args_is_help=True)

_DIAGNOSTIC = re.compile(
    r"^(?P<file>\S+\.(?:fn\.yaml|map\.py)): (?:(?P<rule>rules\[[^:]*\]): )?(?P<message>.*)$", re.S
)


def _diagnostic(severity: str, text: str) -> dict[str, str | None]:
    """One output line as a diagnostic: `file` and `rule` (the `rules[i].rules[j]` path
    the loader reports) when the message starts with them, else just the text."""
    m = _DIAGNOSTIC.match(text)
    if m is None:
        return {"severity": severity, "file": None, "rule": None, "message": text}
    return {
        "severity": severity,
        "file": m["file"],
        "rule": m["rule"],
        "message": m["message"],
    }


def _as_json(run: Callable[[], None]) -> None:
    """Run a command with its output captured and print a single JSON document
    instead: `{"ok", "messages", "diagnostics"}`. Exit code is the command's own."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            run()
        except typer.Exit as exc:
            code = exc.exit_code
    diagnostics: list[dict[str, str | None]] = []
    messages: list[str] = []
    for line in err.getvalue().splitlines():
        if line.startswith("error: "):
            line = line.removeprefix("error: ")
        elif line.startswith("error compiling "):
            line = line.removeprefix("error compiling ")
        diagnostics.append(_diagnostic("error", line))
    for line in out.getvalue().splitlines():
        if line.strip().startswith("warning: "):
            diagnostics.append(_diagnostic("warning", line.strip().removeprefix("warning: ")))
        else:
            messages.append(line)
    typer.echo(
        json.dumps(
            {"ok": code == 0, "messages": messages, "diagnostics": diagnostics},
            ensure_ascii=False,
        )
    )
    if code:
        raise typer.Exit(code=code)


def json_capable(command: Callable[..., None]) -> Callable[..., None]:
    """Give a command the `--json` mode: the command declares a `json_output`
    parameter (`JSON_OPTION`); when set, the run goes through `_as_json`."""

    @functools.wraps(command)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        if kwargs.get("json_output"):
            _as_json(lambda: command(*args, **kwargs))
        else:
            command(*args, **kwargs)

    return wrapper


JSON_OPTION = typer.Option(
    False, "--json", help="Print one JSON document (ok, messages, diagnostics) instead of text"
)


@app.command()
def version() -> None:
    """Print the mapper tool version."""
    from cli._version import ENGINE_VERSION

    typer.echo(ENGINE_VERSION)


@app.command(name="license")
def license_cmd() -> None:
    """Print the engine's license (GPLv3) and the generated-output exception."""
    typer.echo(
        "json2json-mapping-engine  Copyright (C) 2026 Giacomo Furlan\n"
        "This program comes with ABSOLUTELY NO WARRANTY. This is free software, licensed\n"
        "under the GNU General Public License v3.0 (GPLv3); see the LICENSE file, or\n"
        "<https://www.gnu.org/licenses/gpl-3.0.html>, for the full text.\n"
        "\n"
        "Generated output exception: code produced by `mapper build` / `mapper compile`\n"
        "from your mapping rules (PL/SQL, Python, or any other backend target) is not\n"
        "covered by the GPL and may be used under terms of your choosing — only the engine\n"
        "itself is GPLv3. The exact terms are at the end of the LICENSE file."
    )


@app.command()
def stubs() -> None:
    """Generate .pyi/@dataclass artifacts from JSON Schemas, the
    __mapping__ IDE stub, and IDE config files (§IDE setup)."""
    try:
        load_config()  # validate mapper.toml even though stubs don't need it
    except MapperConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if why := synced.refusal(Path.cwd()):
        typer.echo(f"error: {why}", err=True)
        raise typer.Exit(code=1)
    result = generate_stubs()
    typer.echo(
        f"generated {result['input_stubs']} input stub(s), "
        f"{result['output_dataclasses']} output dataclass module(s)"
    )


@app.command(name="functions")
def functions_cmd(
    json_output: bool = typer.Option(
        False, "--json", help='Print {"ok", "functions": [...]} (what the tool\'s explorer reads)'
    ),
) -> None:
    """List the functions a mapping can call: the built-ins and the project's `fn/*.fn`,
    with signature, return type, origin and doc. Always the current list (nothing to keep
    in step by hand)."""
    found = functions_catalogue.function_list(Path.cwd())
    if json_output:
        typer.echo(json.dumps({"ok": True, "functions": found}, ensure_ascii=False))
        return
    for f in found:
        ret = f" -> {f['returns']}" if f["returns"] else ""
        origin = (
            ""
            if f["builtin"]
            else f"  [{f['origin']}{', replaces built-in' if f['replaces_builtin'] else ''}]"
        )
        first = " ".join(f["doc"].split())
        typer.echo(f"{f['signature']}{ret}{origin}" + (f"\n    {first}" if first else ""))


_allow_older_engine = False


@app.callback()
def _options(
    allow_older_engine: Annotated[
        bool,
        typer.Option(
            "--allow-older-engine",
            envvar="J2JME_ALLOW_OLDER_ENGINE",
            help="Work on a project whose mapper.toml names a newer engine than this one "
            "(at your own risk; mapper.toml is never moved back)",
        ),
    ] = False,
) -> None:
    global _allow_older_engine
    _allow_older_engine = allow_older_engine


def _load_config_or_exit(writes: bool = True):
    """The project's config, after the engine-version gate; with `writes`, also the synced-folder
    gate (a build writes under the project)."""
    try:
        config = load_config()
        found = engine_version.status(Path.cwd())
    except MapperConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if writes and (why := synced.refusal(Path.cwd())):
        typer.echo(f"error: {why}", err=True)
        raise typer.Exit(code=1)
    if found.status == "older":
        message = (
            f"mapper.toml is at engine {found.project}, newer than this tool ({found.tool}): "
            "the files may not be read or generated the way that version does"
        )
        if not _allow_older_engine:
            typer.echo(f"error: {message}; use a newer tool, or --allow-older-engine", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"warning: {message}")
    elif found.status != "current":
        was = f"at engine {found.project}" if found.project else "without an engine version"
        typer.echo(
            f"warning: mapper.toml is {was}; this tool is {found.tool}: `mapper upgrade` records it"
        )
    return config


def _target_mappings(file: str | None, config) -> list[Path]:
    if file is not None:
        path = Path(file)
        if not path.is_file():
            typer.echo(f"error: no such file: {file}", err=True)
            raise typer.Exit(code=1)
        return [path]
    mappings = discover_mappings(config)
    if not mappings:
        where = (
            "mappings/functional/*.fn.yaml"
            if config.project.mode == "driven"
            else "mappings/*.map.py"
        )
        typer.echo(f"no mapping files found under {where}")
    return mappings


def _compile_all(config, targets: list[Path], force: bool = False):
    """Compile every mapping (package assembly needs all of them); report
    status for `targets` only. Returns all units."""
    units = []
    for path in discover_mappings(config):
        try:
            result = compile_mapping(path, config, force=force)
        except BuildError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        except Exception as exc:
            typer.echo(f"error compiling {path}: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        units.append(result.unit)
        if path in targets:
            typer.echo(f"{'up-to-date' if result.skipped else 'compiled'}: {path}")
            for w in result.warnings:
                typer.echo(f"  warning: {w}")
    return units


def _compile_and_package(config, file: str | None, force: bool = False) -> None:
    targets = _target_mappings(file, config)
    if not targets:
        return
    units = _compile_all(config, targets, force)
    try:
        written = write_package(units, config)
    except BuildError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"packages: {', '.join(str(p) for p in written)} ({len(units)} mapping(s))")


@app.command()
@json_capable
def transpile(
    file: str | None = typer.Argument(None, help="Single .fn.yaml file to transpile"),
    stage: str | None = typer.Option(
        None,
        "--stage",
        help="Stop after this stage (1-4 or load|build|fuse|emit), writing the stage "
        "artifacts up to it to build/transpiled/stages/<mapping>/ and removing later ones",
    ),
    dump_stages: bool = typer.Option(
        False, "--dump-stages", help="Write the artifacts of all four stages"
    ),
    cached: bool = typer.Option(
        False,
        "--cached",
        help="With --stage: start from the previous stage's artifact when it exists",
    ),
    json_output: bool = JSON_OPTION,
) -> None:
    """Transpile .fn.yaml -> build/transpiled/*.map.py (driven mode only)."""
    if cached and stage is None:
        typer.echo("error: --cached needs --stage", err=True)
        raise typer.Exit(code=2)
    stage_no = None
    if stage is not None:
        try:
            stage_no = parse_stage(stage)
        except FnYamlError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    config = _load_config_or_exit()
    if config.project.mode != "driven":
        typer.echo(
            "error: `mapper transpile` is for mode = 'driven'; in bootstrap mode the "
            ".map.py files are hand-written",
            err=True,
        )
        raise typer.Exit(code=1)
    for path in _target_mappings(file, config):
        warnings: list[str] = []
        notes: list[str] = []
        try:
            transpile_functional(
                path,
                config,
                warnings=warnings,
                stage=stage_no,
                dump_stages=dump_stages,
                cached=cached,
                log=notes,
            )
        except BuildError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        stem = path.name.removesuffix(".fn.yaml")
        for n in notes:
            typer.echo(n)
        if stage_no is not None and stage_no < len(STAGES):
            typer.echo(
                f"stage {stage_no} ({STAGES[stage_no - 1]}): {path} -> "
                f"{artifact(stages_dir(path), stage_no)}"
            )
        else:
            typer.echo(f"transpiled: {path} -> build/transpiled/{stem}.map.py")
        for w in warnings:
            typer.echo(f"  warning: {w}")


@app.command(name="compile")
@json_capable
def compile_cmd(
    file: str | None = typer.Argument(None, help="Report only this mapping (all are packaged)"),
    force: bool = typer.Option(False, "--force", help="Ignore the build cache"),
    json_output: bool = JSON_OPTION,
) -> None:
    """Compile .map.py -> build/compiled/<package>.sql (bootstrap mode)."""
    _compile_and_package(_load_config_or_exit(), file, force)


@app.command()
@json_capable
def build(
    file: str | None = typer.Argument(None, help="Report only this mapping (all are packaged)"),
    json_output: bool = JSON_OPTION,
) -> None:
    """Full build: (transpile if driven +) compile -> build/."""
    config = _load_config_or_exit()
    generate_stubs()
    _compile_and_package(config, file)


@app.command()
@json_capable
def publish(
    to: str | None = typer.Option(
        None,
        "--to",
        help="Folder to publish to (relative to the project, or absolute); else "
        "$J2JME_PUBLISH_DIR, else [publish] dir of mapper.toml, else build/compiled",
    ),
    no_check: bool = typer.Option(
        False,
        "--no-check",
        help="Publish even if the committed build/compiled does not match the sources",
    ),
    json_output: bool = JSON_OPTION,
) -> None:
    """Check, build, then publish the generated files and manifest.json to the publish directory.
    Nothing is published when the check or the build fails (the check is `mapper check`: with the
    artifacts committed they must match the sources, so what is published is what is in git).
    The folder is never emptied: only files the previous manifest listed are removed; the
    manifest is removed first and written last."""
    from cli.build import compiled_files
    from cli.publish import PublishError, publish_dir
    from cli.publish import publish as write_set

    config = _load_config_or_exit()
    if not no_check:
        problems, _ = _artifact_state(config)
        if problems:
            for line in problems:
                typer.echo(f"error: {line}", err=True)
            typer.echo(
                "error: the committed build/compiled does not match the sources: run `mapper "
                "build` and commit, or publish anyway with --no-check",
                err=True,
            )
            raise typer.Exit(code=1)
    generate_stubs()
    _compile_and_package(config, None)
    manifest = read_manifest(compiled_dir())
    dest = publish_dir(config, to, compiled_dir())
    if manifest is None:
        typer.echo(f"error: no manifest in {compiled_dir()} after the build", err=True)
        raise typer.Exit(code=1)
    if dest.resolve() == compiled_dir().resolve():
        typer.echo(f"published: {compiled_dir()} (the build folder, nothing to copy)")
        return
    try:
        written = write_set(compiled_files(config), manifest, dest)
    except (PublishError, BuildError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"published: {len(written) - 1} file(s) and {written[-1].name} in {dest}")


@app.command()
@json_capable
def verify(
    folder: Annotated[
        Path | None,
        typer.Argument(
            help="A published folder; default: the project's publish directory. "
            "Needs no project when given."
        ),
    ] = None,
    json_output: bool = JSON_OPTION,
) -> None:
    """Check a published folder against its manifest.json: every file it lists is there and is
    what was published. For whoever reads the folder, before deploying it. Exit 1 when the set
    is unfinished (no manifest), or a file is missing or changed. Files it does not list are
    not looked at."""
    from cli.publish import publish_dir, verify_folder

    if folder is None:
        folder = publish_dir(_load_config_or_exit(writes=False), None, compiled_dir())
    problems, count = verify_folder(folder)
    if problems:
        for line in problems:
            typer.echo(f"error: {line}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"OK — {count} file(s) in {folder} are what manifest.json says")


@app.command()
def test(
    track: int | None = typer.Option(
        None, "--track", help="1 = offline tests, 2 = integration tests (same as the flags below)"
    ),
    offline: bool = typer.Option(False, "--offline", help="Only the offline tests (--track 1)"),
    integration: bool = typer.Option(
        False, "--integration", help="Only the integration tests (--track 2)"
    ),
    mapping: str | None = typer.Argument(None, help="Integration tests: only this mapping's cases"),
) -> None:
    """Run the offline tests (pytest, no runtime; track 1) and/or the
    integration tests (golden-record tests in the target's own environment,
    an ephemeral Oracle container for PL/SQL; track 2). Without a selector both
    run; the integration tests are skipped with a note when the target's
    environment is not available, the target has none, or there are no cases;
    with --integration / --track 2 any of them is a failure."""
    if offline:
        track = 1
    if integration:
        track = 2
    if offline and integration:
        typer.echo("error: --offline and --integration are mutually exclusive", err=True)
        raise typer.Exit(code=2)
    if track not in (None, 1, 2):
        typer.echo("error: --track must be 1 or 2", err=True)
        raise typer.Exit(code=2)
    config = _load_config_or_exit()
    failed = False

    if track in (None, 1):
        typer.echo("== Offline tests ==")
        code = run_track1()
        if code is None:
            typer.echo("no tests/track1/ suite (offline tests) — skipped")
        elif code != 0:
            failed = True

    if track in (None, 2):
        typer.echo("== Integration tests ==")
        unavailable = integration_state(config)
        if unavailable is not None:
            typer.echo(f"integration tests unavailable: {unavailable}")
            failed = failed or track == 2
        else:
            try:
                results = run_track2(config, mapping, log=typer.echo)
            except Track2Error as exc:
                typer.echo(f"error: {exc}", err=True)
                raise typer.Exit(code=1) from exc
            if not results:
                where = f"tests/golden/{mapping}" if mapping else "tests/golden/<mapping>"
                typer.echo(f"no cases under {where}/*.input.json — skipped")
                # asked for explicitly (as with a missing runtime): nothing ran, not a pass
                failed = failed or track == 2
            for r in results:
                label = f"{r.case.mapping}/{r.case.name}"
                if r.passed is None:
                    typer.echo(f"OUTPUT {label} (no expected file):")
                    typer.echo(json.dumps(r.output, indent=2, ensure_ascii=False))
                elif r.passed:
                    typer.echo(f"PASS   {label}")
                else:
                    failed = True
                    typer.echo(f"FAIL   {label} {r.message}")
                    if r.diff:
                        typer.echo(r.diff)
                for w in r.warnings:
                    typer.echo(f"  warning: allowed: {w}")
                if r.rule_errors:
                    typer.echo(f"  rule errors: {json.dumps(r.rule_errors, ensure_ascii=False)}")
    if failed:
        raise typer.Exit(code=1)


def _artifact_state(config) -> tuple[list[str] | None, int]:
    """What is wrong with the committed `build/compiled` against what the current sources give,
    and how many mappings there are: None instead of a list when git ignores the folder (the
    artifacts are built in CI, so there is nothing to compare). Always recompiles fresh, ignoring
    the build cache; exits when a mapping does not compile."""
    mappings = discover_mappings(config)
    try:
        fresh = assemble([compile_fresh(p, config) for p in mappings], config)
    except Exception as exc:
        typer.echo(f"error compiling: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if artifacts_ignored(compiled_dir()):
        return None, len(mappings)
    suffix = backend_for(config).artifact_suffix
    on_disk = {p.name: p for p in compiled_dir().glob(f"*{suffix}")}
    problems = [f"missing: {compiled_dir() / n}" for n in fresh if n not in on_disk]
    problems += [f"stale: {p} (no longer produced)" for n, p in on_disk.items() if n not in fresh]
    problems += [
        f"out of sync: {p}" for n, p in on_disk.items() if n in fresh and p.read_text() != fresh[n]
    ]
    problems += compare(read_manifest(compiled_dir()), build_manifest(config.project.target, fresh))
    return problems, len(mappings)


@app.command()
@json_capable
def check(json_output: bool = JSON_OPTION) -> None:
    """Verify build/compiled/ is in sync with current sources. Never
    modifies sources or committed files; always recompiles fresh (does not
    trust the build cache, which only tracks source hashes — not whether
    committed output still matches what current sources produce)."""
    problems, count = _artifact_state(_load_config_or_exit())
    if problems is None:  # built in CI, not committed: nothing to compare
        typer.echo(f"OK — {count} mapping(s) build ({compiled_dir()} is git-ignored)")
        return
    if problems:
        for line in problems:
            typer.echo(line)
        typer.echo("run `mapper build`")
        raise typer.Exit(code=1)
    typer.echo(f"OK — {compiled_dir()} is in sync ({count} mapping(s))")


fn_app = typer.Typer(
    no_args_is_help=True, help="Read and write .fn.yaml files as JSON (desktop tool)."
)
app.add_typer(fn_app, name="fn")


@fn_app.command("read")
def fn_read(file: str = typer.Argument(..., help=".fn.yaml file")) -> None:
    """Print the file's Rule Tree as JSON (validated by the strict loader)."""
    try:
        tree = load_functional_file(Path(file))
    except (FnYamlError, OSError) as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}))
        raise typer.Exit(code=1) from exc
    shared.seen(Path.cwd(), Path(file).as_posix())  # a no-op outside a synced folder
    typer.echo(json.dumps({"ok": True, "file": functional_to_dict(tree)}, ensure_ascii=False))


@fn_app.command("check")
def fn_check(file: str = typer.Argument(..., help=".fn.yaml file")) -> None:
    """Check every rule of a file (form, and validity against the project's schemas);
    prints `{"ok", "diagnostics"}`. Exit 1 when a rule has an error."""

    path = Path(file)
    try:
        tree = load_functional_file(path)
    except (FnYamlError, OSError) as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}))
        raise typer.Exit(code=1) from exc
    stem = path.name.removesuffix(".fn.yaml")
    inp, out = schemas_for(Path.cwd(), stem, tree.schemas)
    issues = check_functional(tree, inp, out, all_functions(Path.cwd()))
    failed = any(i.severity == "error" for i in issues)
    typer.echo(
        json.dumps(
            {"ok": not failed, "diagnostics": [i.to_json() for i in issues]}, ensure_ascii=False
        )
    )
    if failed:
        raise typer.Exit(code=1)


@fn_app.command("write")
def fn_write(file: str = typer.Argument(..., help=".fn.yaml file to write")) -> None:
    """Read a Rule Tree as JSON from stdin (the shape `fn read` prints), apply
    validation decay against the file on disk and write it. Prints
    `{"ok": true, "decayed": [rule ids]}`; a tree the loader rejects is not written."""
    import sys

    path = Path(file)
    try:
        new = functional_from_dict(json.load(sys.stdin)["file"])
        decayed: list[str] = []
        touched: set[str] = set()
        if path.is_file():
            old = load_functional_file(path)
            touched = validation_touched_ids(old, new)
            new, decayed = apply_decay_tree(old, new)
        # a validated rule that no longer checks goes back to review (while editing it only
        # shows: the developer may fix it before saving)
        inp, out = schemas_for(Path.cwd(), path.name.removesuffix(".fn.yaml"), new.schemas)
        issues = check_functional(new, inp, out, all_functions(Path.cwd()))
        new, demoted = demote_invalid(
            new, {i.rule for i in issues if i.severity == "error"}, touched
        )
        decayed += demoted
        write_functional(path, new)
        shared.seen(Path.cwd(), path.as_posix())  # a no-op outside a synced folder
    except (FnYamlError, OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({"ok": True, "decayed": decayed}))


import_app = typer.Typer(
    no_args_is_help=True,
    help="Import a functional document (the import-functional-spec skill reads what these commands produce).",
)
app.add_typer(import_app, name="import")


@import_app.command("extract")
def import_extract(
    document: Annotated[Path, typer.Argument(help="xlsx, docx, pdf, txt or md file")],
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Write the JSON here instead of stdout")
    ] = None,
) -> None:
    """Read a document into the normalized form (blocks, resolved tables, formatting, noise flags)."""
    from cli.docread import ExtractError, extract

    try:
        normalized = extract(document)
    except ExtractError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    text = json.dumps(normalized, ensure_ascii=False, indent=2)
    if out is None:
        typer.echo(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "out": str(out),
                "blocks": len(normalized["blocks"]),
                "tables": len(normalized.get("tables", [])),
                "text_layer": normalized.get("text_layer"),
            }
        )
    )


def _import_command(action: str, mapping: str, **kwargs: Any) -> None:
    """Run one of the plan commands from the project directory and print its result as JSON."""
    from cli import import_plan

    try:
        result = getattr(import_plan, action)(Path.cwd(), mapping, **kwargs)
    except (import_plan.PlanError, FnYamlError, OSError) as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result, ensure_ascii=False))
    if not result.get("ok", True):
        raise typer.Exit(code=1)


@import_app.command("assemble")
def import_assemble(
    mapping: Annotated[str, typer.Argument(help="Mapping id (import/<mapping>/)")],
) -> None:
    """Build the working .fn.yaml from the plan's rules, check it, and record each rule's check."""
    _import_command("assemble", mapping)


@import_app.command("test")
def import_test(
    mapping: Annotated[str, typer.Argument(help="Mapping id (import/<mapping>/)")],
) -> None:
    """Run the plan's cases (Python backend) against the working copy and record the results."""
    _import_command("run_cases", mapping)


@import_app.command("apply")
def import_apply(
    mapping: Annotated[str, typer.Argument(help="Mapping id (import/<mapping>/)")],
    force: Annotated[bool, typer.Option("--force", help="Replace an existing .fn.yaml")] = False,
) -> None:
    """Write the checked working copy to mappings/functional/ and mark its rules applied."""
    _import_command("apply", mapping, force=force)


artifacts_app = typer.Typer(
    no_args_is_help=True,
    help="Commit the generated files (build/compiled), or build them in CI instead.",
)
app.add_typer(artifacts_app, name="artifacts")


@artifacts_app.command("status")
def artifacts_status() -> None:
    """Say whether build/compiled is committed or git-ignored."""
    from cli import artifacts_mode

    found = artifacts_mode.state(Path.cwd())
    if found.mode == "unknown":
        typer.echo("not a git repository (or git is not installed): nothing says either way")
    elif found.mode == "ignored":
        left = f"; {len(found.tracked)} file(s) still in the index" if found.tracked else ""
        typer.echo(f"ignored: build/compiled is built by CI, not committed{left}")
    else:
        typer.echo(f"committed: {len(found.tracked)} file(s) of build/compiled in the repository")


@artifacts_app.command("ignore")
def artifacts_ignore() -> None:
    """Stop committing build/compiled: add it to .gitignore and take its files out of the git index
    (they stay on disk; the removal is staged, not committed). CI then builds them."""
    from cli import artifacts_mode

    try:
        before = artifacts_mode.ignore(Path.cwd())
    except MapperConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if before.mode == "ignored" and not before.tracked:
        typer.echo("already ignored")
        return
    typer.echo(
        f"build/compiled is ignored; {len(before.tracked)} file(s) removed from the index "
        "(staged): commit .gitignore and the removal"
    )


@artifacts_app.command("track")
def artifacts_track() -> None:
    """Commit build/compiled again: take it out of .gitignore and stage its files. Run `mapper
    build` first if they are not there."""
    from cli import artifacts_mode

    try:
        artifacts_mode.track(Path.cwd())
    except MapperConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("build/compiled is committed again; its files are staged")


@app.command()
def upgrade() -> None:
    """Record this tool's version as the project's engine (`[project] engine` in mapper.toml),
    when it is newer than the one there. Never lowers it."""
    try:
        before = engine_version.upgrade(Path.cwd())
    except MapperConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if before.status == "current":
        typer.echo(f"mapper.toml is already at engine {before.tool}")
    else:
        was = before.project or "no version"
        typer.echo(f"mapper.toml: engine {was} -> {before.tool}; run `mapper build` to regenerate")


@app.command(name="merge-driver")
def merge_driver(
    base: Annotated[Path, typer.Argument(help="%O: the common ancestor")],
    ours: Annotated[Path, typer.Argument(help="%A: our version; the result is written here")],
    theirs: Annotated[Path, typer.Argument(help="%B: their version")],
    path: Annotated[
        str, typer.Argument(help="%P: the file's path in the tree (for messages)")
    ] = "",
) -> None:
    """Git merge driver for *.fn.yaml (rules matched by id) and fn/*.fn (functions matched by
    name); falls back to a text merge with conflict markers. Exit 1 = conflicts left."""
    from cli.merge_driver import run_driver

    clean, note = run_driver(base, ours, theirs, path or str(ours))
    if note:
        typer.echo(f"{path or ours}: {note}", err=True)
    if not clean:
        raise typer.Exit(code=1)


@app.command(name="merge-driver-install")
def merge_driver_install(
    command: str = typer.Option("mapper", help="How git should call mapper"),
) -> None:
    """Register the *.fn.yaml and *.fn merge driver for this clone (git config + .gitattributes)."""
    from cli.merge_driver import install
    from transpiler.merge import MergeError

    try:
        for line in install(Path.cwd(), command):
            typer.echo(line)
    except MergeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def serve() -> None:
    """Worker for the desktop tool: JSON requests on stdin, one JSON answer per line."""
    from cli.serve import serve as run

    run()


if __name__ == "__main__":
    app()
