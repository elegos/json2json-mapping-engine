"""The PL/SQL backend (docs/ARCHITECTURE.md, §Target backends).

Config (`[target.plsql]`): `schema`, `package`, `error_code` required;
`fn_package`, `fn_prefix`, `fn_suffix`, `export_rule_functions` optional. All mappings of a project become
one package, written to `<package>.sql`.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, ClassVar

from compiler.backends.base import Backend, CodeGenError
from compiler.backends.plsql.builtins import BUILTIN_FUNCTIONS
from compiler.backends.plsql.codegen import PlsqlCodeGenerator, PlsqlUnit
from compiler.backends.plsql.package import assemble_package
from compiler.function_linker import FunctionLinker
from compiler.scope_resolver import ScopeResolution

DEFAULT_PACKAGE = "MAPPING_RULES"
DEFAULT_ERROR_CODE = -20000


class PlsqlBackend(Backend):
    target: ClassVar[str] = "plsql"
    required_keys: ClassVar[tuple[str, ...]] = ("schema", "package", "error_code")
    defaults: ClassVar[dict[str, Any]] = {
        "fn_prefix": "",
        "fn_suffix": "",
        # true = also list every fn_<rule_id> in the package spec (not just
        # map_<id>/map_<id>_safe) — §Generated artifact, "Rule-function visibility".
        "export_rule_functions": False,
    }

    @property
    def package(self) -> str:
        return self.config.get("package", DEFAULT_PACKAGE)

    def compile_module(
        self, tree: ast.Module, mapping_id: str, scope_resolution: ScopeResolution | None = None
    ) -> PlsqlUnit:
        generator = PlsqlCodeGenerator(
            function_linker=FunctionLinker(BUILTIN_FUNCTIONS),
            error_code=int(self.config.get("error_code", DEFAULT_ERROR_CODE)),
        )
        return generator.compile_module(tree, mapping_id, scope_resolution)

    def unit_from_json(self, data: dict[str, Any]) -> PlsqlUnit:
        return PlsqlUnit.from_json(data)

    def assemble(self, units: list[Any]) -> str:
        if not all(isinstance(u, PlsqlUnit) for u in units):
            raise CodeGenError("the plsql backend can only assemble PlsqlUnit objects")
        return assemble_package(
            units, self.package, bool(self.config.get("export_rule_functions", False))
        )

    def artifact_path(self, compiled_dir: Path) -> Path:
        return compiled_dir / f"{self.package.lower()}.sql"
