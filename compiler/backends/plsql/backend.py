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

from compiler.backends.base import Backend, CodeGenError, Option
from compiler.backends.integration import CaseResult, IntegrationContext
from compiler.backends.plsql import integration
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

    options: ClassVar[tuple[Option, ...]] = (
        Option("schema", "string", "Owner of the generated packages", required=True),
        Option(
            "error_code",
            "int",
            "Code of the RAISE_APPLICATION_ERROR raised by the raising entry point",
            required=True,
        ),
        Option(
            "mapping_package_prefix",
            "string",
            "Mapping package name = prefix + MAPPING ID + suffix (one of prefix / suffix, "
            "or the table below)",
        ),
        Option("mapping_package_suffix", "string", "See the prefix"),
        Option(
            "mapping_packages",
            "table",
            "Explicit table: mapping id -> package name (instead of prefix / suffix)",
        ),
        Option(
            "mapping_index_package",
            "string",
            "Extra package forwarding every entry point to the mapping's package",
        ),
        Option(
            "functions_package",
            "string",
            "Shared package of the built-ins that are not 1:1 with PL/SQL",
            default="J2JME_FUNCTIONS",
        ),
        Option(
            "export_rule_functions",
            "bool",
            "List every fn_<mapping>_<rule> in its package spec too",
            default=False,
        ),
        Option("fn_prefix", "string", "Prefix of generated procedure / function names", default=""),
        Option("fn_suffix", "string", "Suffix of generated procedure / function names", default=""),
    )

    # `[target.plsql.test]`: the database the integration tests start (a container)
    test_options: ClassVar[tuple[Option, ...]] = (
        Option(
            "container_image",
            "string",
            "Database container image for `mapper test`",
            default=integration.DEFAULT_IMAGE,
        ),
        Option("container_tag", "string", "Image tag", default=integration.DEFAULT_TAG),
    )
    has_integration: ClassVar[bool] = True

    def integration_unavailable(self) -> str | None:
        return integration.integration_unavailable()

    def run_integration(self, context: IntegrationContext) -> list[CaseResult]:
        return integration.run_integration(self.config, context)

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
