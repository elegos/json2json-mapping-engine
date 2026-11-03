# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportAssignmentType=false, reportOptionalMemberAccess=false, reportIndexIssue=false, reportCallIssue=false
"""Spreadsheet reader: every sheet becomes a title, bands, tables and loose cells, with the
merged ranges resolved and the explicit formatting kept."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from cli.docread import Ids, clean_format


def _rgb(color: Any) -> str | None:
    value = getattr(color, "rgb", None)
    if getattr(color, "type", None) == "rgb" and isinstance(value, str):
        value = value[-6:]
        return None if value in ("000000",) else value
    return None


def _format(cell: Cell) -> dict[str, Any]:
    fill = None
    if cell.fill is not None and cell.fill.fill_type == "solid":
        fill = _rgb(cell.fill.fgColor)
        if fill == "FFFFFF":
            fill = None
    font = cell.font
    return clean_format(
        {
            "fill": fill,
            "font_color": _rgb(font.color) if font is not None else None,
            "bold": bool(font and font.b),
            "italic": bool(font and font.i),
            "strike": bool(font and font.strike),
        }
    )


def _text(cell: Cell) -> str:
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).replace("\xa0", " ")


def _regions(ws: Worksheet) -> list[tuple[int, int, int, int]]:
    """Blocks of consecutive non-empty rows, as (first row, last row, first col, last col)."""
    rows: dict[int, list[int]] = {}
    for row in ws.iter_rows():
        cols = [c.column for c in row if c.value not in (None, "")]
        if cols:
            rows[row[0].row] = cols
    out: list[tuple[int, int, int, int]] = []
    start = prev = None
    lo = hi = 0
    for r in sorted(rows):
        if start is not None and prev is not None and r == prev + 1:
            lo, hi = min(lo, min(rows[r])), max(hi, max(rows[r]))
        else:
            if start is not None and prev is not None:
                out.append((start, prev, lo, hi))
            start, lo, hi = r, min(rows[r]), max(rows[r])
        prev = r
    if start is not None and prev is not None:
        out.append((start, prev, lo, hi))
    return out


def read(path: Path) -> dict[str, Any]:
    wb = load_workbook(path, data_only=False)
    ids = Ids()
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    warnings: list[str] = []
    formulas = 0
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            warnings.append(
                f"sheet '{ws.title}' is {ws.sheet_state} (read anyway; check it is meant to be part of the document)"
            )
        merged: dict[str, str] = {}
        for rng in ws.merged_cells.ranges:
            for row in ws.iter_rows(
                min_row=rng.min_row, max_row=rng.max_row, min_col=rng.min_col, max_col=rng.max_col
            ):
                for c in row:
                    merged[c.coordinate] = rng.coord
        hidden_rows = [r for r, d in ws.row_dimensions.items() if d.hidden]
        hidden_cols = [c for c, d in ws.column_dimensions.items() if d.hidden]
        if hidden_rows:
            warnings.append(f"sheet '{ws.title}': hidden rows {hidden_rows[:10]}")
        if hidden_cols:
            warnings.append(f"sheet '{ws.title}': hidden columns {hidden_cols[:10]}")
        first = True
        for r0, r1, c0, c1 in _regions(ws):
            width = c1 - c0 + 1
            used = sum(
                1
                for r in range(r0, r1 + 1)
                if sum(1 for c in range(c0, c1 + 1) if ws.cell(r, c).value not in (None, "")) > 1
            )
            if width == 1 and r1 - r0 + 1 >= 20:  # a pasted sample or listing: keep its layout
                blocks.append(
                    {
                        "id": ids("b"),
                        "kind": "code",
                        "text": "\n".join(_text(ws.cell(r, c0)) for r in range(r0, r1 + 1)),
                        "location": {
                            "sheet": ws.title,
                            "cells": f"{get_column_letter(c0)}{r0}:{get_column_letter(c0)}{r1}",
                        },
                    }
                )
                first = False
                continue
            if width < 2 or used < 2:  # loose text: one block per row
                for r in range(r0, r1 + 1):
                    cells = [
                        ws.cell(r, c)
                        for c in range(c0, c1 + 1)
                        if ws.cell(r, c).value not in (None, "")
                    ]
                    if not cells:
                        continue
                    text = " | ".join(_text(c) for c in cells)
                    kind = "sheet_title" if first and r == r0 else "paragraph"
                    blocks.append(
                        {
                            "id": ids("b"),
                            "kind": kind,
                            "text": text,
                            "location": {"sheet": ws.title, "cells": cells[0].coordinate},
                            "format": _format(cells[0]),
                        }
                    )
                first = False
                continue
            first = False
            table_id = ids("t")
            rows: list[dict[str, Any]] = []
            for r in range(r0, r1 + 1):
                row_cells: list[dict[str, Any]] = []
                for c in range(c0, c1 + 1):
                    cell = ws.cell(r, c)
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        formulas += 1
                    entry: dict[str, Any] = {
                        "text": _text(cell),
                        "location": {"cells": f"{get_column_letter(c)}{r}"},
                    }
                    fmt = _format(cell)
                    rng = merged.get(cell.coordinate)
                    if rng:
                        entry["merged_from"] = rng
                        origin = ws[rng.split(":")[0]]
                        if origin.coordinate != cell.coordinate:
                            entry["text"] = _text(origin)
                            entry["continuation"] = True
                            fmt = fmt or _format(origin)
                    if fmt:
                        entry["format"] = fmt
                    row_cells.append(entry)
                row: dict[str, Any] = {"cells": row_cells}
                if (
                    width > 1
                    and all(
                        c.get("merged_from") == row_cells[0].get("merged_from") for c in row_cells
                    )
                    and row_cells[0].get("merged_from")
                ):
                    row["band"] = True
                rows.append(row)
            header_rows: list[int] = []
            for idx, row in enumerate(rows):
                if row.get("band"):
                    continue
                if all(c["text"] for c in row["cells"]):
                    header_rows = [idx]
                break
            tables.append(
                {
                    "id": table_id,
                    "location": {
                        "sheet": ws.title,
                        "cells": f"{get_column_letter(c0)}{r0}:{get_column_letter(c1)}{r1}",
                    },
                    "header_rows": header_rows,
                    "rows": rows,
                }
            )
            blocks.append(
                {
                    "id": ids("b"),
                    "kind": "table_ref",
                    "text": "",
                    "table": table_id,
                    "location": {"sheet": ws.title},
                }
            )
        for row in ws.iter_rows():
            for cell in row:
                if cell.comment is not None:
                    blocks.append(
                        {
                            "id": ids("b"),
                            "kind": "note",
                            "text": cell.comment.text.strip(),
                            "location": {"sheet": ws.title, "cells": cell.coordinate},
                        }
                    )
    if formulas:
        warnings.append(
            f"{formulas} cells contain formulas; their text is the formula, not the value"
        )
    props = wb.properties
    metadata = {
        k: v
        for k, v in {
            "title": props.title,
            "author": props.creator,
            "last_modified_by": props.lastModifiedBy,
            "created": props.created.isoformat() if props.created else None,
            "modified": props.modified.isoformat() if props.modified else None,
            "sheets": [ws.title for ws in wb.worksheets],
        }.items()
        if v
    }
    return {
        "metadata": metadata,
        "text_layer": "full",
        "blocks": blocks,
        "tables": tables,
        "warnings": warnings,
    }
