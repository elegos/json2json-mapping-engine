"""`mapper` — build CLI entry point (see docs/ARCHITECTURE.md, §Build CLI).

Fleshed out incrementally: `transpile` lands in M5.
"""

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
    write_package,
)
from cli.config import MapperConfigError, load_config
from cli.stubs import generate_stubs
from cli.track1 import run_track1
from cli.track2 import Track2Error, detect_runtime, run_track2

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


def _target_mappings(file: str | None) -> list[Path]:
    if file is not None:
        path = Path(file)
        if not path.is_file():
            typer.echo(f"error: no such file: {file}", err=True)
            raise typer.Exit(code=1)
        return [path]
    mappings = discover_mappings()
    if not mappings:
        typer.echo("no mapping files found under mappings/*.map.py")
    return mappings


def _compile_all(config, targets: list[Path], force: bool = False):
    """Compile every mapping (package assembly needs all of them); report
    status for `targets` only. Returns all units."""
    units = []
    for path in discover_mappings():
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
    return units


def _compile_and_package(config, file: str | None, force: bool = False) -> None:
    targets = _target_mappings(file)
    if not targets:
        return
    units = _compile_all(config, targets, force)
    try:
        out = write_package(units, config)
    except BuildError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"package: {out} ({len(units)} mapping(s))")


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
    """Full build: (transpile if driven, not yet implemented +) compile -> build/."""
    config = _load_config_or_exit()
    generate_stubs()
    _compile_and_package(config, file)


@app.command()
def test(
    track: int | None = typer.Option(None, "--track", help="1 = unit tests, 2 = target E2E"),
    mapping: str | None = typer.Argument(None, help="Track 2: only this mapping's cases"),
) -> None:
    """Run Track 1 (pytest, no runtime) and/or Track 2 (golden-record tests
    against an ephemeral Oracle container). No --track runs both; Track 2 is
    skipped with a note when no container runtime is available."""
    if track not in (None, 1, 2):
        typer.echo("error: --track must be 1 or 2", err=True)
        raise typer.Exit(code=2)
    config = _load_config_or_exit()
    failed = False

    if track in (None, 1):
        typer.echo("== Track 1 ==")
        code = run_track1()
        if code is None:
            typer.echo("no tests/track1/ suite — skipped")
        elif code != 0:
            failed = True

    if track in (None, 2):
        typer.echo("== Track 2 ==")
        if detect_runtime() is None:
            typer.echo("no podman/docker available — Track 2 unavailable")
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
    mappings = discover_mappings()
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
