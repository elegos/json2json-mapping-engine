"""Compact, sliceable text views of a normalized document, for an assistant that may only run
`mapper`: the JSON of a long spreadsheet is tens of thousands of lines (every cell carries its
location and formatting), these views print one line per row or block and only the formatting that
may carry meaning (fill, font colour, strike-through, highlight)."""

from __future__ import annotations

from typing import Any

MEANING = ("fill", "font_color", "strike", "highlight")
DEFAULT_LIMIT = 60


class ViewError(Exception):
    """A request the document cannot answer (unknown table, empty range)."""


def _flat(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split("\n")).strip()


def _marks(fmt: dict[str, Any] | None, everything: bool) -> str:
    if not fmt:
        return ""
    keys = fmt if everything else {k: v for k, v in fmt.items() if k in MEANING}
    if not keys:
        return ""
    return " {" + ",".join(k if v is True else f"{k}={v}" for k, v in keys.items()) + "}"


def _where(location: dict[str, Any] | None) -> str:
    if not location:
        return ""
    parts = [str(location[k]) for k in ("sheet", "cells") if k in location]
    parts += [
        f"{k} {location[k]}" for k in ("page", "section", "paragraph", "line") if k in location
    ]
    return " ".join(parts)


def _table(doc: dict[str, Any], table_id: str) -> dict[str, Any]:
    for table in doc.get("tables", []):
        if table["id"] == table_id:
            return table
    ids = ", ".join(t["id"] for t in doc.get("tables", [])) or "none"
    raise ViewError(f"no table {table_id!r} (tables: {ids})")


def _row_line(index: int, row: dict[str, Any], everything: bool) -> str:
    cells = row["cells"]
    where = _where(cells[0].get("location")) if cells else ""
    if row.get("band"):
        return f"r{index} {where} BAND: {_flat(cells[0]['text'])}{_marks(cells[0].get('format'), everything)}"
    shown = []
    for cell in cells:
        text = "^" if cell.get("continuation") else _flat(cell["text"])
        shown.append(text + _marks(cell.get("format"), everything))
    return f"r{index} {where} | " + " | ".join(shown)


def outline(doc: dict[str, Any]) -> str:
    out = [f"file: {doc['file']} ({doc['format']}), text layer: {doc.get('text_layer', 'full')}"]
    meta = doc.get("metadata") or {}
    for key in ("title", "author", "modified", "sheets"):
        if meta.get(key):
            out.append(f"{key}: {meta[key]}")
    for warning in doc.get("warnings", []):
        out.append(f"warning: {warning}")
    blocks = doc["blocks"]
    kinds: dict[str, int] = {}
    for block in blocks:
        kinds[block["kind"]] = kinds.get(block["kind"], 0) + 1
    out.append(f"blocks: {len(blocks)} (" + ", ".join(f"{k} {n}" for k, n in kinds.items()) + ")")
    out.append(f"tables: {len(doc.get('tables', []))}")
    for table in doc.get("tables", []):
        rows = table["rows"]
        out.append(f"  {table['id']}  {_where(table.get('location'))}  {len(rows)} rows")
        for h in table.get("header_rows", [])[:3]:
            out.append("    header " + _row_line(h, rows[h], False))
    heads = [b for b in blocks if b["kind"] in ("title", "heading", "sheet_title")]
    if heads:
        out.append("headings:")
        for b in heads[:80]:
            out.append(f"  {b['id']} {b['kind']}{b.get('level', '')} {_flat(b['text'])}")
        if len(heads) > 80:
            out.append(f"  ... {len(heads) - 80} more (blocks --kind heading)")
    return "\n".join(out)


def rows(
    doc: dict[str, Any],
    table_id: str,
    start: int = 0,
    end: int | None = None,
    everything: bool = False,
) -> str:
    table = _table(doc, table_id)
    total = len(table["rows"])
    stop = min(total, end + 1 if end is not None else start + DEFAULT_LIMIT)
    if start < 0 or start >= total:
        raise ViewError(f"{table_id} has {total} rows (r0..r{total - 1})")
    out = [_row_line(i, table["rows"][i], everything) for i in range(start, stop)]
    out.append(
        f"-- {table_id} r{start}..r{stop - 1} of {total}"
        + (f"; next: --from {stop}" if stop < total else "; end of table")
    )
    return "\n".join(out)


def blocks(
    doc: dict[str, Any],
    start: int = 0,
    end: int | None = None,
    kind: str | None = None,
    everything: bool = False,
) -> str:
    items = [b for b in doc["blocks"] if kind is None or b["kind"] == kind]
    total = len(items)
    stop = min(total, end + 1 if end is not None else start + DEFAULT_LIMIT)
    if start < 0 or start >= max(total, 1):
        raise ViewError(f"{total} blocks match (0..{total - 1})")
    out = []
    for n in range(start, stop):
        b = items[n]
        label = f"{b['kind']}{b.get('level', '')}"
        text = f"-> table {b['table']}" if b["kind"] == "table_ref" else _flat(b["text"])
        noise = " (noise)" if b.get("noise") else ""
        out.append(
            f"#{n} {b['id']} {label} {_where(b.get('location'))}{noise}: {text}"
            + _marks(b.get("format"), everything)
        )
    out.append(
        f"-- blocks #{start}..#{stop - 1} of {total}"
        + (f"; next: --from {stop}" if stop < total else "; end")
    )
    return "\n".join(out)


def find(doc: dict[str, Any], needle: str, limit: int = 40) -> str:
    low = needle.lower()
    hits: list[str] = []
    for table in doc.get("tables", []):
        for i, row in enumerate(table["rows"]):
            if any(low in c["text"].lower() and not c.get("continuation") for c in row["cells"]):
                hits.append(f"{table['id']} " + _row_line(i, row, False))
    for b in doc["blocks"]:
        if b["kind"] != "table_ref" and low in b["text"].lower():
            hits.append(f"{b['id']} {b['kind']} {_where(b.get('location'))}: {_flat(b['text'])}")
    shown = hits[:limit]
    shown.append(
        f"-- {len(hits)} match(es) for {needle!r}"
        + (f", first {limit} shown" if len(hits) > limit else "")
    )
    return "\n".join(shown)
