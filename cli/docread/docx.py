# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportAssignmentType=false, reportOptionalMemberAccess=false, reportIndexIssue=false, reportCallIssue=false
"""Word reader: paragraphs, headings, lists and tables in document order, headers/footers
(as noise) and footnotes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from cli.docread import Ids, clean_format

_MONO = ("courier", "consolas", "mono", "menlo")
_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _runs_format(par: Paragraph) -> dict[str, Any]:
    runs = [r for r in par.runs if r.text.strip()]
    if not runs:
        return {}

    def every(attr: str) -> bool:
        return all(bool(getattr(r.font, attr)) for r in runs)

    fonts = {(r.font.name or par.style.font.name or "").lower() for r in runs}
    colors = {
        str(r.font.color.rgb)
        for r in runs
        if r.font.color is not None and r.font.color.rgb is not None
    }
    highlights = {
        r.font.highlight_color.name.lower() for r in runs if r.font.highlight_color is not None
    }
    return clean_format(
        {
            "bold": every("bold"),
            "italic": every("italic"),
            "strike": every("strike"),
            "monospace": all(any(m in f for m in _MONO) for f in fonts),
            "font_color": colors.pop() if len(colors) == 1 and colors != {"000000"} else None,
            "highlight": highlights.pop() if len(highlights) == 1 else None,
        }
    )


def _kind(par: Paragraph, fmt: dict[str, Any]) -> tuple[str, int | None]:
    name = (par.style.name or "").lower()
    if name == "title":
        return "title", None
    if name.startswith("heading"):
        digits = "".join(ch for ch in name if ch.isdigit())
        return "heading", int(digits) if digits else 1
    if "list" in name or par._p.pPr is not None and par._p.pPr.numPr is not None:
        return "list_item", None
    if fmt.get("monospace") or "code" in name:
        return "code", None
    return "paragraph", None


def _cell_fill(tc: Any) -> str | None:
    shd = tc.tcPr.find(f"{_NS}shd") if tc.tcPr is not None else None
    fill = shd.get(f"{_NS}fill") if shd is not None else None
    return None if fill in (None, "auto", "FFFFFF") else fill


def _table(table: Table, table_id: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    # the cells already met, by their XML element (kept alive: a freed element's `id()` is reused)
    seen: dict[Any, str] = {}
    for r_idx, row in enumerate(table.rows):
        cells: list[dict[str, Any]] = []
        for c_idx, cell in enumerate(row.cells):
            key = cell._tc
            entry: dict[str, Any] = {"text": cell.text.strip()}
            fmt = clean_format(
                {
                    "fill": _cell_fill(cell._tc),
                    **(_runs_format(cell.paragraphs[0]) if cell.paragraphs else {}),
                }
            )
            if key in seen:
                entry["merged_from"] = seen[key]
                entry["continuation"] = True
            else:
                seen[key] = f"r{r_idx}c{c_idx}"
                grid = cell._tc.grid_span
                if grid > 1 or cell._tc.vMerge is not None:
                    entry["merged_from"] = seen[key]
            if fmt:
                entry["format"] = fmt
            cells.append(entry)
        row_out: dict[str, Any] = {"cells": cells}
        if (
            len(cells) > 1
            and all(c.get("merged_from") == cells[0].get("merged_from") for c in cells)
            and cells[0].get("merged_from")
        ):
            row_out["band"] = True
        rows.append(row_out)
    header = [0] if rows and all(c["text"] for c in rows[0]["cells"]) else []
    return {"id": table_id, "header_rows": header, "rows": rows}


def read(path: Path) -> dict[str, Any]:
    doc = Document(str(path))
    ids = Ids()
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    warnings: list[str] = []
    section = ""
    par_no = 0
    for child in doc.element.body.iterchildren():
        if child.tag == f"{_NS}p":
            par = Paragraph(child, doc)
            text = par.text.strip()
            if not text:
                continue
            fmt = _runs_format(par)
            kind, level = _kind(par, fmt)
            if kind in ("title", "heading"):
                section = text
            block: dict[str, Any] = {
                "id": ids("b"),
                "kind": kind,
                "text": par.text if kind == "code" else text,
                "location": {"paragraph": par_no, **({"section": section} if section else {})},
            }
            if level:
                block["level"] = level
            if fmt:
                block["format"] = fmt
            blocks.append(block)
            par_no += 1
        elif child.tag == f"{_NS}tbl":
            table_id = ids("t")
            tables.append(
                {
                    **_table(Table(child, doc), table_id),
                    "location": {"section": section} if section else {},
                }
            )
            blocks.append(
                {
                    "id": ids("b"),
                    "kind": "table_ref",
                    "text": "",
                    "table": table_id,
                    "location": {"section": section} if section else {},
                }
            )
    for s_idx, sec in enumerate(doc.sections):
        for label, part in (("header", sec.header), ("footer", sec.footer)):
            text = " | ".join(p.text.strip() for p in part.paragraphs if p.text.strip())
            if text and not part.is_linked_to_previous:
                blocks.append(
                    {
                        "id": ids("b"),
                        "kind": "header_footer",
                        "text": text,
                        "noise": True,
                        "location": {"section": f"{label} {s_idx + 1}"},
                    }
                )
    for part in doc.part.package.iter_parts():
        if str(part.partname) == "/word/footnotes.xml":
            from lxml import etree

            root = etree.fromstring(part.blob)
            for note in root.iter(f"{_NS}footnote"):
                if note.get(f"{_NS}type"):
                    continue
                text = "".join(t.text or "" for t in note.iter(f"{_NS}t")).strip()
                if text:
                    blocks.append(
                        {
                            "id": ids("b"),
                            "kind": "note",
                            "text": text,
                            "location": {"section": f"footnote {note.get(f'{_NS}id')}"},
                        }
                    )
    props = doc.core_properties
    metadata = {
        k: v
        for k, v in {
            "title": props.title,
            "author": props.author,
            "last_modified_by": props.last_modified_by,
            "created": props.created.isoformat() if props.created else None,
            "modified": props.modified.isoformat() if props.modified else None,
            "revision": props.revision,
        }.items()
        if v
    }
    if doc.element.xpath("//w:ins | //w:del"):
        warnings.append(
            "the document has tracked changes; the text shown may mix inserted and deleted wording"
        )
    return {
        "metadata": metadata,
        "text_layer": "full",
        "blocks": blocks,
        "tables": tables,
        "warnings": warnings,
    }
