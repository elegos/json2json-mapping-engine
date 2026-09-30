"""PL/SQL package assembly (docs/ARCHITECTURE.md, §Generated artifact).

Every mapping is its own package, `<package of the mapping>` (naming.py): its entry
points `map_<id>`, `map_<id>_safe`, and `map_<id>_fn` when a rule declares `@parallel`,
plus its rule functions `fn_<id>_<rule>`. The rule functions are package-private unless
`export_rule_functions` is set (then they are in the spec too).

With `mapping_index_package` there is one more package that only forwards: it declares
every entry point of every mapping with the same signature and calls the mapping's
package, so callers always go through one place.

The result is one artifact file per package (`<package lower>.sql`), in deploy order:
mapping packages by id, the index package last. Changing a mapping rewrites and recompiles
only its own package; the index depends on the specs, which do not change with a body.
"""

from __future__ import annotations

import re

from compiler.backends.base import CodeGenError
from compiler.backends.plsql.builtins import LIBRARY_FUNCTIONS
from compiler.backends.plsql.codegen import PlsqlSubprogram, PlsqlUnit, _indent_block
from compiler.backends.plsql.naming import PlsqlNaming

_PARAM = re.compile(r"\b(p_\w+)\s+(?:IN|OUT)\b")


def _package(naming: PlsqlNaming, name: str, spec_items: list[str], body_items: list[str]) -> str:
    spec = "\n\n".join(_indent_block(i) for i in spec_items)
    body = "\n\n".join(_indent_block(i) for i in body_items)
    qualified = naming.qualified(name)
    return (
        f"CREATE OR REPLACE PACKAGE {qualified} AS\n{spec}\nEND {name};\n/\n\n"
        f"CREATE OR REPLACE PACKAGE BODY {qualified} AS\n{body}\nEND {name};\n/\n"
    )


def _forwarder(target_package: str, entry: PlsqlSubprogram) -> str:
    """Body of an entry point that calls the same entry point of `target_package`."""
    args = ", ".join(_PARAM.findall(entry.spec))
    call = f"{target_package}.{entry.name}({args})"
    statement = f"RETURN {call};" if entry.spec.startswith("FUNCTION") else f"{call};"
    return f"{entry.spec.removesuffix(';')} AS\nBEGIN\n    {statement}\nEND {entry.name};"


def _functions_package(naming: PlsqlNaming, used: list[str]) -> str:
    """The shared functions package: the built-ins that mappings call by name."""
    specs = [f"FUNCTION {n}({LIBRARY_FUNCTIONS[n].spec};" for n in used]
    bodies = [
        f"FUNCTION {n}({LIBRARY_FUNCTIONS[n].spec} IS\nBEGIN\n"
        f"    {LIBRARY_FUNCTIONS[n].body_text()}\nEND {n};"
        for n in used
    ]
    return _package(naming, naming.functions_package, specs, bodies)


def assemble_packages(
    units: list[PlsqlUnit], naming: PlsqlNaming, export_rule_functions: bool = False
) -> dict[str, str]:
    """File name -> text, in deploy order."""
    seen: dict[str, PlsqlUnit] = {}
    for unit in units:
        if unit.mapping_id in seen:
            raise CodeGenError(
                f"duplicate mapping id '{unit.mapping_id}' — ids must be unique across the "
                "project (they namespace the subprograms)"
            )
        seen[unit.mapping_id] = unit
    if naming.mapping_packages is not None:
        unknown = sorted(set(naming.mapping_packages) - set(seen))
        if unknown:
            raise CodeGenError(
                f"[target.plsql.mapping_packages] names unknown mapping(s): {', '.join(unknown)}"
            )

    ordered = sorted(units, key=lambda u: u.mapping_id)  # stable output, independent of file order
    owners: dict[str, str] = {}
    files: dict[str, str] = {}
    used = sorted({name for unit in ordered for name in unit.library_functions})
    if used:  # deployed first: the mapping packages call it
        files[f"{naming.functions_package.lower()}.sql"] = _functions_package(naming, used)
    for unit in ordered:
        package = naming.package_for(unit.mapping_id)
        if package.upper() in {
            n.upper() for n in (naming.functions_package, naming.index_package) if n
        }:
            raise CodeGenError(
                f"mapping '{unit.mapping_id}' uses {package}, which is the "
                "functions_package or mapping_index_package"
            )
        if package.upper() in owners:
            raise CodeGenError(
                f"mappings '{owners[package.upper()]}' and '{unit.mapping_id}' both map to "
                f"package {package}"
            )
        owners[package.upper()] = unit.mapping_id
        # Rule functions first in the body: a package body needs a name declared before use.
        spec_items = [f.spec for f in unit.rule_functions] if export_rule_functions else []
        spec_items += [e.spec for e in unit.entry_points]
        body_items = [f.body for f in unit.rule_functions] + [e.body for e in unit.entry_points]
        files[f"{package.lower()}.sql"] = _package(naming, package, spec_items, body_items)

    if naming.index_package:
        entries = [
            (naming.qualified(naming.package_for(u.mapping_id)), e)
            for u in ordered
            for e in u.entry_points
        ]
        files[f"{naming.index_package.lower()}.sql"] = _package(
            naming,
            naming.index_package,
            [e.spec for _, e in entries],
            [_forwarder(package, e) for package, e in entries],
        )
    return files
