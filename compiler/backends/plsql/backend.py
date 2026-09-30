"""The PL/SQL backend (docs/ARCHITECTURE.md, §Target backends).

Config (`[target.plsql]`): `schema`, `error_code` required, and the choice of
how mappings map to packages (`[target.plsql.mapping_packages]` or
`mapping_package_prefix` / `_suffix`); `mapping_index_package`, `fn_prefix`,
`fn_suffix`, `export_rule_functions` optional; names are derived in `naming.py`.
Every mapping becomes its own package, written to `<package lower>.sql`.
"""

from __future__ import annotations

import ast
from typing import Any, ClassVar

from compiler.backends.base import Backend, CodeGenError
from compiler.backends.plsql.builtins import BUILTIN_FUNCTIONS
from compiler.backends.plsql.codegen import PlsqlCodeGenerator, PlsqlUnit
from compiler.backends.plsql.naming import PlsqlNaming
from compiler.backends.plsql.package import assemble_packages
from compiler.function_linker import FunctionLinker
from compiler.scope_resolver import ScopeResolution

DEFAULT_ERROR_CODE = -20000


class PlsqlBackend(Backend):
    target: ClassVar[str] = "plsql"
    required_keys: ClassVar[tuple[str, ...]] = ("schema", "error_code")
    defaults: ClassVar[dict[str, Any]] = {
        "fn_prefix": "",
        "fn_suffix": "",
        # true = also list every fn_<rule_id> in the package spec (not just
        # map_<id>/map_<id>_safe) — §Generated artifact, "Rule-function visibility".
        "export_rule_functions": False,
    }

    @classmethod
    def validate_config(cls, section: dict[str, Any]) -> None:
        PlsqlNaming.from_config(section, strict=True)

    @property
    def naming(self) -> PlsqlNaming:
        return PlsqlNaming.from_config(self.config)

    def compile_module(
        self, tree: ast.Module, mapping_id: str, scope_resolution: ScopeResolution | None = None
    ) -> PlsqlUnit:
        generator = PlsqlCodeGenerator(
            function_linker=FunctionLinker(BUILTIN_FUNCTIONS),
            error_code=int(self.config.get("error_code", DEFAULT_ERROR_CODE)),
            naming=self.naming,
        )
        return generator.compile_module(tree, mapping_id, scope_resolution)

    def unit_from_json(self, data: dict[str, Any]) -> PlsqlUnit:
        return PlsqlUnit.from_json(data)

    def assemble(self, units: list[Any]) -> dict[str, str]:
        if not all(isinstance(u, PlsqlUnit) for u in units):
            raise CodeGenError("the plsql backend can only assemble PlsqlUnit objects")
        return assemble_packages(
            units, self.naming, bool(self.config.get("export_rule_functions", False))
        )

    def deploy_order(self, file_names: list[str]) -> list[str]:
        return self.naming.deploy_order(file_names)
