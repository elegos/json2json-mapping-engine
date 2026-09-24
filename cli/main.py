"""`mapper` — build CLI entry point (see docs/ARCHITECTURE.md, §Build CLI).

Fleshed out incrementally: `transpile`/`test --track 2` land in M4/M5.
"""

from __future__ import annotations

from pathlib import Path

import typer

from cli.build import (
    BuildError,
    compile_fresh,
    compile_mapping,
    discover_mappings,
)
from cli.config import MapperConfigError, load_config
from cli.stubs import generate_stubs

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


@app.command(name="compile")
def compile_cmd(
    file: str | None = typer.Argument(None, help="Single mapping file to compile"),
    force: bool = typer.Option(False, "--force", help="Ignore the build cache"),
) -> None:
    """Compile .map.py -> build/compiled/*.sql (bootstrap mode)."""
    config = _load_config_or_exit()
    for path in _target_mappings(file):
        try:
            result = compile_mapping(path, config, force=force)
        except BuildError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        except Exception as exc:
            typer.echo(f"error compiling {path}: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        status = "up-to-date" if result.skipped else "compiled"
        typer.echo(f"{status}: {path} -> {result.path}")


@app.command()
def build(
    file: str | None = typer.Argument(None, help="Single mapping file to build"),
) -> None:
    """Full build: (transpile if driven, not yet implemented +) compile -> build/."""
    config = _load_config_or_exit()
    generate_stubs()
    for path in _target_mappings(file):
        try:
            result = compile_mapping(path, config)
        except BuildError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        except Exception as exc:
            typer.echo(f"error compiling {path}: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        status = "up-to-date" if result.skipped else "compiled"
        typer.echo(f"{status}: {path} -> {result.path}")


@app.command()
def check() -> None:
    """Verify build/compiled/ is in sync with current sources. Never
    modifies sources or committed files; always recompiles fresh (does not
    trust the build cache, which only tracks source hashes — not whether
    committed output still matches what current sources produce)."""
    config = _load_config_or_exit()
    mappings = discover_mappings()
    ok = True
    for path in mappings:
        stem = path.stem.removesuffix(".map")
        committed = Path("build/compiled") / f"{stem}.sql"
        try:
            fresh_sql = compile_fresh(path, config)
        except Exception as exc:
            typer.echo(f"error compiling {path}: {exc}", err=True)
            ok = False
            continue
        if not committed.is_file():
            typer.echo(f"missing: {committed} (run `mapper build`)")
            ok = False
            continue
        if committed.read_text() != fresh_sql:
            typer.echo(f"out of sync: {committed} (run `mapper build`)")
            ok = False
    if not ok:
        raise typer.Exit(code=1)
    typer.echo(f"OK — build/compiled/ is in sync ({len(mappings)} mapping(s))")


if __name__ == "__main__":
    app()
