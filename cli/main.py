"""`mapper` — build CLI entry point (see docs/ARCHITECTURE.md, §Build CLI).

Fleshed out incrementally: `stubs`/`compile`/`build`/`check`/`transpile`/`test`
land as the compiler, schema generator, and transpiler stages become available.
"""

from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the mapper tool version."""
    from importlib.metadata import version as pkg_version

    try:
        typer.echo(pkg_version("json2json-mapping-engine"))
    except Exception:
        typer.echo("0.1.0 (dev)")


if __name__ == "__main__":
    app()
