"""PL/SQL package assembly (docs/ARCHITECTURE.md, §Generated artifact).

All mappings of a project live in ONE package. Callers invoke
`<package>.map_<id>(p_src, p_out)` / `<package>.map_<id>_safe(...)`; rule
functions (`fn_<mapping_id>_<rule_id>`, namespaced by mapping id because rule
ids are only unique within a mapping) are package-private unless
`export_rule_functions` is set. With `fn_package` they move to a second package,
emitted first (the main body calls them, so they are always in its spec);
`schema` qualifies the `CREATE`d packages. Names: `naming.py`.

Trade-off worth knowing: one package means any mapping change recompiles the
whole package body on deploy and invalidates its dependents. Splitting into
several packages would need a grouping key in `mapper.toml`; not offered yet.
"""

from __future__ import annotations

from compiler.backends.base import CodeGenError
from compiler.backends.plsql.codegen import PlsqlUnit, _indent_block
from compiler.backends.plsql.naming import PlsqlNaming


def _package(naming: PlsqlNaming, name: str, spec_items: list[str], body_items: list[str]) -> str:
    spec = "\n\n".join(_indent_block(i) for i in spec_items)
    body = "\n\n".join(_indent_block(i) for i in body_items)
    qualified = naming.qualified(name)
    return (
        f"CREATE OR REPLACE PACKAGE {qualified} AS\n{spec}\nEND {name};\n/\n\n"
        f"CREATE OR REPLACE PACKAGE BODY {qualified} AS\n{body}\nEND {name};\n/\n"
    )


def assemble_package(
    units: list[PlsqlUnit], naming: PlsqlNaming, export_rule_functions: bool = False
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
    rules = [f for unit in ordered for f in unit.rule_functions]
    entries = [e for unit in ordered for e in unit.entry_points]

    if naming.fn_package:
        if naming.fn_package.upper() == naming.package.upper():
            raise CodeGenError("[target.plsql] fn_package must differ from package")
        return (
            _package(naming, naming.fn_package, [f.spec for f in rules], [f.body for f in rules])
            + "\n"
            + _package(naming, naming.package, [e.spec for e in entries], [e.body for e in entries])
        )

    # Rule functions first in the body: a package body needs a name declared before use.
    spec_items = [f.spec for f in rules] if export_rule_functions else []
    spec_items += [e.spec for e in entries]
    return _package(
        naming, naming.package, spec_items, [f.body for f in rules] + [e.body for e in entries]
    )
