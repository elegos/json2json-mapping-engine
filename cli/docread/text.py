"""Plain text and Markdown reader."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cli.docread import Ids

_BULLET = re.compile(r"^\s*([-*+]|\d+[.)])\s+")


def _pipe_row(line: str) -> list[str] | None:
    if "|" not in line:
        return None
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return None if len(cells) < 2 else cells


def read(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    ids = Ids()
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    lines = raw.splitlines()
    i = 0
    par: list[str] = []
    par_start = 0

    def flush() -> None:
        nonlocal par
        if par:
            blocks.append(
                {
                    "id": ids("b"),
                    "kind": "paragraph",
                    "text": " ".join(s.strip() for s in par),
                    "location": {"line": par_start},
                }
            )
            par = []

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush()
            start = i
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append(
                {
                    "id": ids("b"),
                    "kind": "code",
                    "text": "\n".join(code),
                    "location": {"line": start},
                }
            )
        elif m := re.match(r"^(#{1,6})\s+(.*)$", line):
            flush()
            blocks.append(
                {
                    "id": ids("b"),
                    "kind": "heading",
                    "level": len(m.group(1)),
                    "text": m.group(2).strip(),
                    "location": {"line": i},
                }
            )
        elif (
            _pipe_row(line) and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1])
        ):
            flush()
            rows = [{"cells": [{"text": t} for t in _pipe_row(line) or []]}]
            start = i
            i += 2
            while i < len(lines) and _pipe_row(lines[i]):
                rows.append({"cells": [{"text": t} for t in _pipe_row(lines[i]) or []]})
                i += 1
            table_id = ids("t")
            tables.append(
                {"id": table_id, "location": {"line": start}, "header_rows": [0], "rows": rows}
            )
            blocks.append(
                {
                    "id": ids("b"),
                    "kind": "table_ref",
                    "text": "",
                    "table": table_id,
                    "location": {"line": start},
                }
            )
            continue
        elif not line.strip():
            flush()
        elif _BULLET.match(line):
            flush()
            blocks.append(
                {
                    "id": ids("b"),
                    "kind": "list_item",
                    "text": _BULLET.sub("", line).strip(),
                    "location": {"line": i},
                }
            )
        else:
            if not par:
                par_start = i
            par.append(line)
        i += 1
    flush()
    return {"text_layer": "full", "blocks": blocks, "tables": tables, "warnings": []}
