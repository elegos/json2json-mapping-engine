"""The document readers: every fixture document reads into a valid normalized document, and the
details the skill relies on (merged cells, formatting, noise, missing text layer) are there."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from cli.docread import ExtractError, extract
from cli.main import app

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "import"
SCHEMA = json.loads(
    (ROOT / "skills/import-functional-spec/references/normalized-document.schema.json").read_text()
)
DOCUMENTS = sorted(
    p
    for p in FIXTURES.rglob("*")
    if p.suffix in (".xlsx", ".docx", ".pdf") and "_hidden" not in p.parts
)


def _doc(name: str) -> dict:
    return extract(next(p for p in DOCUMENTS if p.name.startswith(name)))


def _cells(doc: dict) -> list[dict]:
    return [c for t in doc["tables"] for r in t["rows"] for c in r["cells"]]


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda p: p.name)
def test_every_fixture_document_reads_into_a_valid_normalized_document(path: Path) -> None:
    doc = extract(path)
    jsonschema.Draft202012Validator(SCHEMA).validate(doc)
    assert doc["file"] == path.name
    refs = {b["table"] for b in doc["blocks"] if b["kind"] == "table_ref"}
    assert refs == {t["id"] for t in doc["tables"]}


def test_a_spreadsheet_keeps_colours_and_merged_cells() -> None:
    doc = _doc("Mapping_ReservationToTask")
    fills = {c["format"]["fill"] for c in _cells(doc) if "fill" in c.get("format", {})}
    assert {"FFFF00", "00B0F0"} <= fills
    assert any(c.get("continuation") for c in _cells(doc)) or any(
        r.get("band") for t in doc["tables"] for r in t["rows"]
    )


def test_a_word_table_keeps_strike_through_and_highlight() -> None:
    cells = _cells(_doc("QuoteToOrder"))
    assert any(c.get("format", {}).get("strike") for c in cells)
    assert any(c.get("format", {}).get("highlight") == "yellow" for c in cells)


def test_a_long_pasted_listing_is_one_block() -> None:
    doc = _doc("QuoteToOrder")
    listing = [b for b in doc["blocks"] if b["kind"] == "code" and b["location"].get("lines")]
    assert listing and all(b["location"]["lines"] >= 20 for b in listing)


def test_running_headers_are_marked_as_noise() -> None:
    doc = _doc("MeterReport")
    noise = [b for b in doc["blocks"] if b.get("noise")]
    assert noise and all(b["kind"] == "header_footer" for b in noise)
    assert not any(b.get("noise") for b in doc["blocks"] if b["kind"] == "code")


def test_pseudo_code_in_a_pdf_is_code() -> None:
    doc = _doc("MeterReport")
    assert any(b["kind"] == "code" and ":=" in b["text"] for b in doc["blocks"])


def test_a_scanned_pdf_has_no_text_layer() -> None:
    doc = _doc("ParcelLabel")
    assert doc["text_layer"] == "none" and doc["blocks"] == [] and doc["warnings"]


def test_a_word_table_without_merged_cells_has_no_continuation_cells(tmp_path: Path) -> None:
    from docx import Document

    doc = Document()
    table = doc.add_table(rows=6, cols=4)
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            cell.text = f"r{r}c{c}"
    doc.save(str(tmp_path / "t.docx"))
    cells = [c for r in extract(tmp_path / "t.docx")["tables"][0]["rows"] for c in r["cells"]]
    assert len(cells) == 24 and not any("continuation" in c or "merged_from" in c for c in cells)


def test_a_word_document_without_tables_reads_as_paragraphs() -> None:
    doc = _doc("Spec_DeliveryNotice")
    assert doc["tables"] == [] and sum(b["kind"] == "paragraph" for b in doc["blocks"]) > 5


def test_text_and_markdown_with_a_table(tmp_path: Path) -> None:
    md = tmp_path / "spec.md"
    md.write_text(
        "# Title\n\nSome rule.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- item\n", encoding="utf-8"
    )
    doc = extract(md)
    jsonschema.Draft202012Validator(SCHEMA).validate(doc)
    assert [b["kind"] for b in doc["blocks"]] == ["heading", "paragraph", "table_ref", "list_item"]
    assert doc["tables"][0]["rows"][1]["cells"][1]["text"] == "2"


def test_unsupported_and_missing_files_are_reported(tmp_path: Path) -> None:
    with pytest.raises(ExtractError, match="unsupported"):
        extract(tmp_path / "x.odt")
    with pytest.raises(ExtractError, match="not found"):
        extract(tmp_path / "x.docx")
    broken = tmp_path / "broken.xlsx"
    broken.write_text("not a workbook")
    with pytest.raises(ExtractError, match="cannot read"):
        extract(broken)


def test_the_command_writes_the_file_and_a_status_line(tmp_path: Path) -> None:
    out = tmp_path / "n" / "doc.json"
    path = next(p for p in DOCUMENTS if p.name.startswith("MeterReport"))
    result = CliRunner().invoke(app, ["import", "extract", str(path), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ok"] is True
    assert json.loads(out.read_text())["format"] == "pdf"
    bad = CliRunner().invoke(app, ["import", "extract", str(tmp_path / "nope.pdf")])
    assert bad.exit_code == 1


def _view(tmp_path: Path, name: str, *args: str) -> tuple[int, str]:
    document = tmp_path / "document.json"
    document.write_text(json.dumps(_doc(name)), encoding="utf-8")
    result = CliRunner().invoke(app, ["import", args[0], str(document), *args[1:]])
    return result.exit_code, result.output


def test_views_read_a_long_document_in_slices(tmp_path: Path) -> None:
    code, out = _view(tmp_path, "Mapping_ReservationToTask", "outline")
    assert (
        code == 0
        and "t2  Mapping A9:E30  22 rows" in out
        and "header r1 A10 | Target Element" in out
    )

    code, out = _view(
        tmp_path, "Mapping_ReservationToTask", "rows", "t2", "--from", "2", "--to", "3"
    )
    lines = out.strip().splitlines()
    assert lines[0].startswith("r2 A11 | domain | Y | Fixed = D")
    assert lines[-1] == "-- t2 r2..r3 of 22; next: --from 4"

    code, out = _view(tmp_path, "Mapping_ReservationToTask", "rows", "t2", "--from", "20")
    assert out.strip().endswith("end of table")

    code, out = _view(tmp_path, "Mapping_ReservationToTask", "find", "queueId")
    assert "t1 r4 A5 | queueId" in out and "2 match(es)" in out


def test_views_say_what_is_missing(tmp_path: Path) -> None:
    code, out = _view(tmp_path, "Mapping_ReservationToTask", "rows", "t99")
    assert code == 1 and "no table 't99'" in out
    assert _view(tmp_path, "Mapping_ReservationToTask", "rows", "t2", "--from", "500")[0] == 1
