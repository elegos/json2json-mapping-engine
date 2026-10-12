"""The import skill's contracts: the schemas are valid, the examples and the fixtures conform."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills/import-functional-spec"
REFS = SKILL / "references"
EXAMPLES = ROOT / "docs/import/examples"
FIXTURES = ROOT / "tests/fixtures/import"


def _load(path: Path):
    return json.loads(path.read_text())


def _validator(name: str) -> jsonschema.Draft202012Validator:
    schema = _load(REFS / name)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


@pytest.mark.parametrize("example", sorted(EXAMPLES.glob("*.ir.json")), ids=lambda p: p.name)
def test_ir_examples_conform(example: Path) -> None:
    _validator("ir.schema.json").validate(_load(example))


def test_profile_example_conforms() -> None:
    profile = yaml.safe_load((EXAMPLES / "wb1.profile.yaml").read_text())
    _validator("profile.schema.json").validate(profile)


def test_normalized_document_example_conforms() -> None:
    _validator("normalized-document.schema.json").validate(
        _load(EXAMPLES / "normalized_excerpt.json")
    )


def test_skill_has_front_matter_and_names_its_references() -> None:
    text = (SKILL / "SKILL.md").read_text()
    head = re.match(r"---\nname: (?P<name>[\w-]+)\ndescription: (?P<desc>.+)\n---\n", text)
    assert head and head["name"] == "import-functional-spec" and len(head["desc"]) > 40
    for ref in re.findall(r"`(references/[\w.-]+)`", text):
        assert (SKILL / ref).is_file(), ref


def _fixture_schemas() -> list[tuple[Path, Path, Path]]:
    """(folder, input schema, output schema) for every folder that has both."""
    found = []
    for folder in sorted({p.parent for p in FIXTURES.rglob("*.input.schema.json")}):
        out = list(folder.glob("*.output.schema.json"))
        if out:
            found.append((folder, next(folder.glob("*.input.schema.json")), out[0]))
    return found


def test_the_fixture_folders_were_found() -> None:
    names = {f.name for f, _, _ in _fixture_schemas()}
    assert {
        "wb1_reservation_task",
        "wb7_quote_order_docx",
        "_hidden",
        "customer_to_contact",
    } <= names


@pytest.mark.parametrize("folder,inp,out", _fixture_schemas(), ids=lambda v: getattr(v, "name", ""))
def test_fixture_cases_conform_to_their_schemas(folder: Path, inp: Path, out: Path) -> None:
    tests = folder / "tests"
    assert tests.is_dir(), folder
    cases = sorted(tests.glob("case*.in.json"))
    assert cases, folder
    for case in cases:
        jsonschema.validate(_load(case), _load(inp))
        expected = _load(case.with_name(case.name.replace(".in.", ".out.")))
        if "__rejected__" in expected:  # the fixture's convention for "no output produced"
            continue
        jsonschema.validate(expected, _load(out))
