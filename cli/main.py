"""`mapper` — build CLI entry point (see docs/ARCHITECTURE.md, §Build CLI)."""

from __future__ import annotations

import contextlib
import functools
import io
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from cli.build import (
    BUILD_COMPILED_DIR,
    BuildError,
    assemble,
    compile_fresh,
    compile_mapping,
    discover_mappings,
    stages_dir,
    transpile_functional,
    write_package,
)
from cli.config import MapperConfigError, load_config
from cli.stubs import generate_stubs
from cli.track1 import run_track1
from cli.track2 import Track2Error, detect_runtime, run_track2, runtime_diagnostic
from transpiler.model import (
    FnYamlError,
    functional_from_dict,
    functional_to_dict,
    load_functional_file,
)
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
    from importlib.metadata import version as pkg_version

    try:
        typer.echo(pkg_version("json2json-mapping-engine"))
    except Exception:
        typer.echo("0.1.0 (dev)")


@app.command()
def stubs() -> None:
    """Generate .pyi/@dataclass artifacts from JSON Schemas, the
    __mapping__ IDE stub, and IDE config files (§IDE setup)."""
    try:
        load_config()  # validate mapper.toml even though stubs don't need it
    except MapperConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    result = generate_stubs()
    typer.echo(
        f"generated {result['input_stubs']} input stub(s), "
        f"{result['output_dataclasses']} output dataclass module(s)"
    )


def _load_config_or_exit():
    try:
        return load_config()
    except MapperConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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
    integration tests (golden-record tests against an ephemeral Oracle
    container; track 2). Without a selector both run; the integration tests
    are skipped with a note when no container runtime is available or there
    are no cases; with --integration / --track 2 either one is a failure."""
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
        if detect_runtime() is None:
            typer.echo("no podman/docker available — integration tests unavailable")
            typer.echo(f"  {runtime_diagnostic()}")
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


@app.command()
@json_capable
def check(json_output: bool = JSON_OPTION) -> None:
    """Verify build/compiled/ is in sync with current sources. Never
    modifies sources or committed files; always recompiles fresh (does not
    trust the build cache, which only tracks source hashes — not whether
    committed output still matches what current sources produce)."""
    config = _load_config_or_exit()
    mappings = discover_mappings(config)
    try:
        fresh = assemble([compile_fresh(p, config) for p in mappings], config)
    except Exception as exc:
        typer.echo(f"error compiling: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    on_disk = {p.name: p for p in BUILD_COMPILED_DIR.glob("*.sql")}
    problems = [f"missing: {BUILD_COMPILED_DIR / n}" for n in fresh if n not in on_disk]
    problems += [f"stale: {p} (no longer produced)" for n, p in on_disk.items() if n not in fresh]
    problems += [
        f"out of sync: {p}" for n, p in on_disk.items() if n in fresh and p.read_text() != fresh[n]
    ]
    if problems:
        for line in problems:
            typer.echo(line)
        typer.echo("run `mapper build`")
        raise typer.Exit(code=1)
    typer.echo(f"OK — {BUILD_COMPILED_DIR} is in sync ({len(mappings)} mapping(s))")


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
    typer.echo(json.dumps({"ok": True, "file": functional_to_dict(tree)}, ensure_ascii=False))


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
        if path.is_file():
            new, decayed = apply_decay_tree(load_functional_file(path), new)
        write_functional(path, new)
    except (FnYamlError, OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({"ok": True, "decayed": decayed}))


if __name__ == "__main__":
    app()
