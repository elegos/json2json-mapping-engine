"""JSON Schema → generated Python artifacts (docs/ARCHITECTURE.md, §Type system,
§Input type contract, §Output type contract).

Input schemas (`schemas/input/*.json`) produce `.pyi` stubs in
`generated/stubs/` — read-only type surfaces for `root`/`src`.
Output schemas (`schemas/output/*.json`) produce `@dataclass` modules in
`generated/dataclasses/` — the writable, validated surface for `out`.

String sizing for the PL/SQL backend (`maxLength` <= 4000 → VARCHAR2(n CHAR),
else CLOB) is a Code Generator concern (M2), not this module's — this module
emits target-agnostic Python typing derived from the schema and leaves
`maxLength` in the schema files for the backend to re-read directly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

JsonSchema = dict[str, Any]

_PRIMITIVE_MAP = {
    "integer": "int",
    "boolean": "bool",
}


class SchemaGeneratorError(Exception):
    """Raised for schemas the generator cannot translate into DSL types."""


def _pascal_case(name: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Anon"


@dataclass
class ClassDef:
    name: str
    fields: list[FieldDef] = field(default_factory=list)


@dataclass
class FieldDef:
    name: str
    type_expr: str
    required: bool


@dataclass
class SchemaTypes:
    """Structured (non-text) view of a resolved schema, for the Type
    Checker (compiler/type_checker.py) — avoids re-parsing the generated
    `.pyi`/`.py` text back into a type table."""

    root_type: str
    classes: dict[str, ClassDef]


def resolve_schema_types(schema: JsonSchema, root_name: str) -> SchemaTypes:
    walker = _SchemaWalker(root_name)
    root_type = walker.resolve_root(schema)
    return SchemaTypes(root_type=root_type, classes={c.name: c for c in walker.classes})


class _SchemaWalker:
    """Walks a JSON Schema, emitting one ClassDef per object/oneOf-alternative
    encountered, in the order they were first referenced (children first, so
    a straight top-to-bottom emission needs no forward references)."""

    def __init__(self, root_name: str):
        self.root_name = root_name
        self.classes: list[ClassDef] = []
        self._seen_names: set[str] = set()

    def resolve_root(self, schema: JsonSchema) -> str:
        return self._resolve(schema, self.root_name)

    def _unique_name(self, candidate: str) -> str:
        name = candidate
        i = 2
        while name in self._seen_names:
            name = f"{candidate}{i}"
            i += 1
        self._seen_names.add(name)
        return name

    def _is_nullable(self, schema: JsonSchema) -> bool:
        if schema.get("nullable") is True:
            return True
        t = schema.get("type")
        return bool(isinstance(t, list) and "null" in t)

    def _non_null_type(self, schema: JsonSchema) -> Any:
        t = schema.get("type")
        if isinstance(t, list):
            non_null = [x for x in t if x != "null"]
            return non_null[0] if len(non_null) == 1 else non_null
        return t

    def _resolve(self, schema: JsonSchema, hint_name: str) -> str:
        """Returns a Python type expression string for `schema`."""
        nullable = self._is_nullable(schema)

        if "oneOf" in schema or "anyOf" in schema:
            alternatives: list[JsonSchema] = schema.get("oneOf") or schema.get("anyOf") or []
            alt_exprs = []
            for i, alt in enumerate(alternatives):
                if alt.get("type") == "null":
                    nullable = True
                    continue
                alt_name = _pascal_case(alt.get("title") or f"{hint_name}Alt{i + 1}")
                alt_exprs.append(self._resolve(alt, alt_name))
            expr = " | ".join(alt_exprs) if len(alt_exprs) > 1 else alt_exprs[0]
            return f"{expr} | None" if nullable else expr

        base_type = self._non_null_type(schema)
        if isinstance(base_type, list):
            raise SchemaGeneratorError(f"unsupported multi-type union {base_type!r} in schema")

        if base_type == "object":
            # patternProperties / no fixed `properties` → opaque JsonObj fallback.
            if "properties" not in schema and (
                "patternProperties" in schema
                or schema.get("additionalProperties") not in (False, None)
            ):
                expr = "JsonObj"
            else:
                expr = self._resolve_object(schema, hint_name)
        elif base_type == "array":
            item_schema = schema.get("items", {})
            item_name = _pascal_case(hint_name.rstrip("s") or hint_name)
            item_expr = self._resolve(item_schema, item_name) if item_schema else "JsonObj"
            expr = f"list[{item_expr}]"
        elif base_type == "string":
            fmt = schema.get("format")
            if fmt == "date":
                expr = "date"
            elif fmt == "date-time":
                expr = "datetime"
            else:
                expr = "str"
        elif base_type == "number":
            expr = "number"
        elif base_type in _PRIMITIVE_MAP:
            expr = _PRIMITIVE_MAP[base_type]
        elif base_type is None:
            expr = "JsonObj"
        else:
            raise SchemaGeneratorError(f"unsupported JSON Schema type {base_type!r}")

        return f"{expr} | None" if nullable else expr

    def _resolve_object(self, schema: JsonSchema, hint_name: str) -> str:
        class_name = self._unique_name(_pascal_case(schema.get("title") or hint_name))
        properties: dict[str, JsonSchema] = schema.get("properties", {})
        required: set[str] = set(schema.get("required", []))

        cls = ClassDef(name=class_name)
        for prop_name, prop_schema in properties.items():
            field_hint = _pascal_case(f"{hint_name}{prop_name}")
            type_expr = self._resolve(prop_schema, field_hint)
            cls.fields.append(
                FieldDef(name=prop_name, type_expr=type_expr, required=prop_name in required)
            )
        self.classes.append(cls)
        return class_name


_HEADER = "# generated by `mapper stubs` from {source} — do not edit manually\n"
_DSL_TYPE_NAMES = ("JsonObj", "date", "datetime", "number")


def _used_dsl_types(classes: list[ClassDef]) -> list[str]:
    used = {
        name
        for cls in classes
        for f in cls.fields
        for name in _DSL_TYPE_NAMES
        if re.search(rf"\b{name}\b", f.type_expr)
    }
    return [name for name in _DSL_TYPE_NAMES if name in used]


def _render_classes_as_stub(classes: list[ClassDef]) -> str:
    lines: list[str] = []
    for cls in classes:
        lines.append(f"class {cls.name}:")
        if not cls.fields:
            lines.append("    ...")
        for f in cls.fields:
            lines.append(f"    {f.name}: {f.type_expr}")
        lines.append("")
    return "\n".join(lines)


def generate_input_stub(schema: JsonSchema, root_name: str, source: str = "<schema>") -> str:
    """Generate a `.pyi` stub for an input JSON Schema (§Input type contract)."""
    walker = _SchemaWalker(root_name)
    root_type = walker.resolve_root(schema)

    body = _render_classes_as_stub(walker.classes)
    header = _HEADER.format(source=source)
    used = _used_dsl_types(walker.classes)
    imports = f"from runtime.dsl_types import {', '.join(used)}\n\n" if used else ""
    footer = f"\n{root_name}: type = {root_type}\n" if root_type != _pascal_case(root_name) else ""
    return header + imports + body + footer


def _render_classes_as_dataclasses(classes: list[ClassDef]) -> str:
    lines: list[str] = []
    for cls in classes:
        required = [f for f in cls.fields if f.required]
        optional = [f for f in cls.fields if not f.required]
        lines.append("@dataclass")
        lines.append(f"class {cls.name}:")
        if not cls.fields:
            lines.append("    pass")
        for f in required:
            lines.append(f"    {f.name}: {f.type_expr}")
        for f in optional:
            type_expr = f.type_expr if f.type_expr.endswith("| None") else f"{f.type_expr} | None"
            lines.append(f"    {f.name}: {type_expr} = None")
        lines.append("")
    return "\n".join(lines)


def generate_output_dataclasses(
    schema: JsonSchema, root_name: str, source: str = "<schema>"
) -> str:
    """Generate a `@dataclass` module for an output JSON Schema (§Output type contract)."""
    walker = _SchemaWalker(root_name)
    root_type = walker.resolve_root(schema)
    if root_type != (walker.classes[-1].name if walker.classes else None):
        raise SchemaGeneratorError("output schema root must be a JSON object")

    header = _HEADER.format(source=source)
    used = _used_dsl_types(walker.classes)
    dsl_import = f"from runtime.dsl_types import {', '.join(used)}\n" if used else ""
    imports = f"from dataclasses import dataclass\n{dsl_import}\n"
    body = _render_classes_as_dataclasses(walker.classes)
    return header + imports + body


def generate_input_schemas(input_dir: Path, out_dir: Path) -> list[Path]:
    """Batch entry point: schemas/input/*.json -> generated/stubs/*.pyi"""
    written = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for schema_path in sorted(input_dir.glob("*.json")):
        schema = json.loads(schema_path.read_text())
        root_name = _pascal_case(schema_path.stem)
        stub = generate_input_stub(schema, root_name, source=str(schema_path))
        out_path = out_dir / f"{schema_path.stem}.pyi"
        out_path.write_text(stub)
        written.append(out_path)
    return written


def generate_output_schemas(output_dir: Path, out_dir: Path) -> list[Path]:
    """Batch entry point: schemas/output/*.json -> generated/dataclasses/*.py"""
    written = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for schema_path in sorted(output_dir.glob("*.json")):
        schema = json.loads(schema_path.read_text())
        root_name = _pascal_case(schema_path.stem)
        module = generate_output_dataclasses(schema, root_name, source=str(schema_path))
        out_path = out_dir / f"{schema_path.stem}.py"
        out_path.write_text(module)
        written.append(out_path)
    return written
