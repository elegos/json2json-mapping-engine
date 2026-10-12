"""Readers that turn a functional document into the normalized document
(`skills/import-functional-spec/references/normalized-document.schema.json`).

They only read: no interpretation (colours, numbering, conventions) happens here. The format
libraries are an optional extra (`uv sync --extra import`) and are imported when needed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

SUFFIXES = {
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".docx": "docx",
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "text",
}


class ExtractError(Exception):
    """The file cannot be read (unsupported format, missing library, damaged file)."""


class Ids:
    """Sequential ids (`b1`, `t1`...) so that references stay stable for one file."""

    def __init__(self) -> None:
        self._n: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        self._n[prefix] = self._n.get(prefix, 0) + 1
        return f"{prefix}{self._n[prefix]}"


def clean_format(fmt: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in fmt.items() if v not in (None, False, "")}


LONG_RUN = 20


def collapse_code(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join a long run of consecutive code lines (a pasted JSON sample, an appendix schema) into
    one block; short runs stay line by line because each line is usually a rule."""
    out: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []

    def flush() -> None:
        if len(run) >= LONG_RUN:
            first = dict(run[0])
            first["text"] = "\n".join(b["text"] for b in run)
            first["location"] = {**first.get("location", {}), "lines": len(run)}
            out.append(first)
        else:
            out.extend(run)
        run.clear()

    for block in blocks:
        if block["kind"] == "code":
            run.append(block)
        else:
            flush()
            out.append(block)
    flush()
    return out


def extract(path: Path) -> dict[str, Any]:
    """Read `path` and return the normalized document (a plain dict, JSON-ready)."""
    fmt = SUFFIXES.get(path.suffix.lower())
    if fmt is None:
        raise ExtractError(
            f"{path.name}: unsupported format '{path.suffix}' (supported: {', '.join(sorted(SUFFIXES))})"
        )
    if not path.is_file():
        raise ExtractError(f"{path}: file not found")
    try:
        if fmt == "xlsx":
            from cli.docread import xlsx as reader
        elif fmt == "docx":
            from cli.docread import docx as reader
        elif fmt == "pdf":
            from cli.docread import pdf as reader
        else:
            from cli.docread import text as reader
    except ImportError as exc:
        raise ExtractError(
            f"reading {fmt} needs an optional library ({exc.name}); install with `uv sync --extra import`"
        ) from exc
    try:
        body = reader.read(path)
    except ExtractError:
        raise
    except Exception as exc:  # damaged or password-protected files raise many kinds of errors
        raise ExtractError(f"{path.name}: cannot read the {fmt} file ({exc})") from exc
    doc: dict[str, Any] = {
        "norm_version": 1,
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "format": fmt,
    }
    doc.update(body)
    doc["blocks"] = collapse_code(doc["blocks"])
    doc.setdefault("warnings", [])
    return doc
