"""PL/SQL package assembly (docs/ARCHITECTURE.md, §Generated artifact).

All mappings of a project live in ONE package. Callers invoke
`<package>.map_<id>(p_src, p_out)` / `<package>.map_<id>_safe(...)`; rule
functions (`fn_<mapping_id>_<rule_id>`, namespaced by mapping id because rule
ids are only unique within a mapping) are package-private unless
`export_rule_functions` is set.

Trade-off worth knowing: one package means any mapping change recompiles the
whole package body on deploy and invalidates its dependents. Splitting into
several packages would need a grouping key in `mapper.toml`; not offered yet.
"""

from __future__ import annotations

from compiler.backends.base import CodeGenError
from compiler.backends.plsql.codegen import PlsqlUnit, _indent_block


def assemble_package(
    units: list[PlsqlUnit], package: str, export_rule_functions: bool = False
) -> str:
    seen: dict[str, PlsqlUnit] = {}
    for unit in units:
        if unit.mapping_id in seen:
            raise CodeGenError(
                f"duplicate mapping id '{unit.mapping_id}' — ids must be unique across the "
                "project (they namespace the package's subprograms)"
            )
        seen[unit.mapping_id] = unit

    ordered = sorted(units, key=lambda u: u.mapping_id)  # stable output, independent of file order
    spec_items: list[str] = []
    body_items: list[str] = []
    for unit in ordered:
        if export_rule_functions:
            spec_items.extend(f.spec for f in unit.rule_functions)
        spec_items.extend(e.spec for e in unit.entry_points)
        # Rule functions first: a package body needs a name declared before use.
        body_items.extend(f.body for f in unit.rule_functions)
        body_items.extend(e.body for e in unit.entry_points)

    spec = "\n\n".join(_indent_block(i) for i in spec_items)
    body = "\n\n".join(_indent_block(i) for i in body_items)
    return (
        f"CREATE OR REPLACE PACKAGE {package} AS\n{spec}\nEND {package};\n/\n\n"
        f"CREATE OR REPLACE PACKAGE BODY {package} AS\n{body}\nEND {package};\n/\n"
    )
