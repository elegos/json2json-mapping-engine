"""PDF reader: the text layer, line by line, with running headers/footers marked as noise.
Tables are not reconstructed (their cells arrive as consecutive lines) and a document without a
text layer is reported as such: this module never does OCR."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTFigure, LTImage, LTTextContainer, LTTextLine

from cli.docread import Ids, clean_format

_MONO = ("courier", "consolas", "mono", "menlo")
_BULLET = re.compile(r"^\s*([-*•–]|\d+[.)])\s+")


def _lines(page: Any) -> tuple[list[dict[str, Any]], bool]:
    out: list[dict[str, Any]] = []
    has_image = False

    def walk(items: Any) -> None:
        nonlocal has_image
        for item in items:
            if isinstance(item, LTImage):
                has_image = True
            elif isinstance(item, LTTextLine):
                text = item.get_text().rstrip("\n")
                chars = [c for c in item if isinstance(c, LTChar)]
                if not text.strip() or not chars:
                    continue
                name = chars[0].fontname.lower()
                out.append(
                    {
                        "text": text.strip(),
                        "top": page.height - item.y1,
                        "size": round(max(c.size for c in chars), 1),
                        "bold": "bold" in name or "black" in name,
                        "italic": "italic" in name or "oblique" in name,
                        "mono": any(m in name for m in _MONO),
                    }
                )
            elif isinstance(item, (LTTextContainer, LTFigure)):
                walk(item)

    walk(page)
    out.sort(key=lambda ln: (round(ln["top"] / 2), ln["top"]))
    return out, has_image


def _shape(text: str) -> str:
    return re.sub(r"\d+", "#", text.lower())


def read(path: Path) -> dict[str, Any]:
    pages: list[tuple[float, list[dict[str, Any]], bool]] = []
    for page in extract_pages(str(path), laparams=LAParams()):
        lines, image = _lines(page)
        pages.append((page.height, lines, image))
    ids = Ids()
    warnings: list[str] = []
    with_text = sum(1 for _, ln, _ in pages if ln)
    if not pages or with_text == 0:
        warnings.append(
            "no text layer: the pages are images and need OCR, which this reader does not do"
        )
        return {"text_layer": "none", "blocks": [], "tables": [], "warnings": warnings}
    layer = "full" if with_text == len(pages) else "partial"
    if layer == "partial":
        empty = [i + 1 for i, (_, ln, _) in enumerate(pages) if not ln]
        warnings.append(f"pages without a text layer: {empty}")
    # running headers/footers: the same text shape near the top or bottom on most pages
    noise: set[str] = set()
    if len(pages) > 1:
        seen: Counter[str] = Counter()
        for height, lines, _ in pages:
            for ln in lines:
                if ln["top"] < height * 0.08 or ln["top"] > height * 0.92:
                    seen[_shape(ln["text"])] += 1
        noise = {s for s, n in seen.items() if n >= max(2, len(pages) * 0.6)}
    sizes = Counter(
        ln["size"] for _, lines, _ in pages for ln in lines if _shape(ln["text"]) not in noise
    )
    body = sizes.most_common(1)[0][0] if sizes else 10
    blocks: list[dict[str, Any]] = []
    for number, (height, lines, _) in enumerate(pages, start=1):
        for idx, ln in enumerate(lines):
            is_noise = _shape(ln["text"]) in noise and (
                ln["top"] < height * 0.08 or ln["top"] > height * 0.92
            )
            if is_noise:
                kind = "header_footer"
            elif ln["mono"]:
                kind = "code"
            elif ln["size"] >= body * 1.15 and (ln["bold"] or ln["size"] >= body * 1.4):
                kind = "heading"
            elif _BULLET.match(ln["text"]):
                kind = "list_item"
            else:
                kind = "paragraph"
            block: dict[str, Any] = {
                "id": ids("b"),
                "kind": kind,
                "text": ln["text"],
                "location": {"page": number, "line": idx},
            }
            fmt = clean_format(
                {
                    "bold": ln["bold"] and kind != "heading",
                    "italic": ln["italic"],
                    "monospace": ln["mono"],
                }
            )
            if fmt:
                block["format"] = fmt
            if is_noise:
                block["noise"] = True
            blocks.append(block)
    warnings.append("tables are not reconstructed: cells of a table arrive as consecutive lines")
    return {"text_layer": layer, "blocks": blocks, "tables": [], "warnings": warnings}
