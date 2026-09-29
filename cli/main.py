"""`mapper` — build CLI entry point (see docs/ARCHITECTURE.md, §Build CLI)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from cli.build import (
    BuildError,
    assemble,
    compile_fresh,
    compile_mapping,
    discover_mappings,
    package_path,
    stages_dir,
    transpile_functional,
    write_package,
)
from cli.config import MapperConfigError, load_config
from cli.stubs import generate_stubs
from cli.track1 import run_track1
from cli.track2 import Track2Error, detect_runtime, run_track2, runtime_diagnostic
from transpiler.model import FnYamlError
from transpiler.stages import STAGES, artifact, parse_stage

app = typer.Typer(add_completion=False, no_args_is_help=True)


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
        out = write_package(units, config)
    except BuildError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"package: {out} ({len(units)} mapping(s))")


@app.command()
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
def compile_cmd(
    file: str | None = typer.Argument(None, help="Report only this mapping (all are packaged)"),
    force: bool = typer.Option(False, "--force", help="Ignore the build cache"),
) -> None:
    """Compile .map.py -> build/compiled/<package>.sql (bootstrap mode)."""
    _compile_and_package(_load_config_or_exit(), file, force)


@app.command()
def build(
    file: str | None = typer.Argument(None, help="Report only this mapping (all are packaged)"),
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
    are skipped with a note when no container runtime is available."""
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
                typer.echo("no cases under tests/golden/<mapping>/*.input.json — skipped")
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
def check() -> None:
    """Verify build/compiled/ is in sync with current sources. Never
    modifies sources or committed files; always recompiles fresh (does not
    trust the build cache, which only tracks source hashes — not whether
    committed output still matches what current sources produce)."""
    config = _load_config_or_exit()
    mappings = discover_mappings(config)
    committed = package_path(config)
    try:
        fresh = assemble([compile_fresh(p, config) for p in mappings], config)
    except Exception as exc:
        typer.echo(f"error compiling: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not committed.is_file():
        typer.echo(f"missing: {committed} (run `mapper build`)")
        raise typer.Exit(code=1)
    if committed.read_text() != fresh:
        typer.echo(f"out of sync: {committed} (run `mapper build`)")
        raise typer.Exit(code=1)
    typer.echo(f"OK — {committed} is in sync ({len(mappings)} mapping(s))")


if __name__ == "__main__":
    app()
