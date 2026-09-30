"""Names of the generated PL/SQL objects (docs/backends/plsql.md, §Configuration).

One place derives every name from `[target.plsql]`, so the generator, the
package assembly and the integration harness cannot disagree:

    entry points   <fn_prefix>map_<id>[_safe|_fn]<fn_suffix>
    rule functions <fn_prefix>fn_<id>_<rule><fn_suffix>
    packages       one per mapping, [<schema>.]<package of the mapping>,
                   the functions package [<schema>.]<functions_package> (built-ins that are
                   not 1:1 with PL/SQL; only when a mapping uses one),
                   and, when set, the index package [<schema>.]<mapping_index_package>

A mapping's package holds its entry points and its rule functions. How a mapping id
becomes a package name is chosen in exactly one of two ways:

    [target.plsql.mapping_packages]      explicit:  orders = "ORDERS_PKG"
    mapping_package_prefix / _suffix     generated: <prefix><ID><suffix>, upper-cased

A project (`strict`) must choose; a bare `PlsqlNaming()` (tests, single-mapping
compiles) falls back to the generated form with an empty prefix and suffix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from compiler.backends.base import CodeGenError

_PREFIX = re.compile(r"([A-Za-z][A-Za-z0-9_$#]*)?")
_SUFFIX = re.compile(r"[A-Za-z0-9_$#]*")
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_$#]*")

_MAX_IDENTIFIER_BYTES = 128

DEFAULT_FUNCTIONS_PACKAGE = "J2JME_FUNCTIONS"


def _checked(key: str, value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise CodeGenError(
            f"[target.plsql] {key} = {value!r} is not a valid Oracle identifier part "
            "(letters, digits, _, $, #; names start with a letter)"
        )
    return value


def _package_name(what: str, value: str) -> str:
    _checked(what, value, _NAME)
    if len(value.encode()) > _MAX_IDENTIFIER_BYTES:
        raise CodeGenError(f"{what} = {value!r} exceeds Oracle's {_MAX_IDENTIFIER_BYTES} bytes")
    return value


@dataclass(frozen=True)
class PlsqlNaming:
    schema: str | None = None
    prefix: str = ""
    suffix: str = ""
    # explicit mode: mapping id -> package (None = generated mode)
    mapping_packages: dict[str, str] | None = None
    package_prefix: str = ""
    package_suffix: str = ""
    index_package: str | None = None
    functions_package: str = DEFAULT_FUNCTIONS_PACKAGE

    @staticmethod
    def from_config(config: dict[str, Any], strict: bool = False) -> PlsqlNaming:
        schema = config.get("schema")
        index = config.get("mapping_index_package")
        explicit = config.get("mapping_packages")
        generated = "mapping_package_prefix" in config or "mapping_package_suffix" in config
        if explicit is not None and generated:
            raise CodeGenError(
                "[target.plsql]: choose either [target.plsql.mapping_packages] or "
                "mapping_package_prefix / mapping_package_suffix, not both"
            )
        if strict and explicit is None and not generated:
            raise CodeGenError(
                "[target.plsql]: say how mappings map to packages: a "
                '[target.plsql.mapping_packages] table (<mapping id> = "PACKAGE") or '
                "mapping_package_prefix / mapping_package_suffix"
            )
        packages: dict[str, str] | None = None
        if explicit is not None:
            if not isinstance(explicit, dict):
                raise CodeGenError("[target.plsql] mapping_packages must be a table")
            packages = {
                str(k): _package_name(f"mapping_packages.{k}", v) for k, v in explicit.items()
            }
            names = [v.upper() for v in packages.values()]
            if len(set(names)) != len(names):
                raise CodeGenError("[target.plsql] mapping_packages: two mappings share a package")
        pkg_prefix = _checked(
            "mapping_package_prefix", config.get("mapping_package_prefix", ""), _PREFIX
        )
        pkg_suffix = _checked(
            "mapping_package_suffix", config.get("mapping_package_suffix", ""), _SUFFIX
        )
        if strict and generated and not (pkg_prefix or pkg_suffix):
            raise CodeGenError(
                "[target.plsql]: mapping_package_prefix and mapping_package_suffix are both empty"
            )
        functions = _package_name(
            "functions_package", config.get("functions_package", DEFAULT_FUNCTIONS_PACKAGE)
        )
        if index is not None and index.upper() == functions.upper():
            raise CodeGenError(
                "[target.plsql] mapping_index_package and functions_package are the same"
            )
        return PlsqlNaming(
            schema=None if schema is None else _checked("schema", schema, _NAME),
            prefix=_checked("fn_prefix", config.get("fn_prefix", ""), _PREFIX),
            suffix=_checked("fn_suffix", config.get("fn_suffix", ""), _SUFFIX),
            mapping_packages=packages,
            package_prefix=pkg_prefix,
            package_suffix=pkg_suffix,
            index_package=(
                None if index is None else _package_name("mapping_index_package", index)
            ),
            functions_package=functions,
        )

    def qualified(self, package: str) -> str:
        """`SCHEMA.package`, or just `package` without a schema."""
        return f"{self.schema}.{package}" if self.schema else package

    def package_for(self, mapping_id: str) -> str:
        """The package that holds this mapping."""
        if self.mapping_packages is not None:
            try:
                return self.mapping_packages[mapping_id]
            except KeyError:
                raise CodeGenError(
                    f"mapping '{mapping_id}' has no package in [target.plsql.mapping_packages]"
                ) from None
        return _package_name(
            f"package of mapping '{mapping_id}'",
            f"{self.package_prefix}{mapping_id}{self.package_suffix}".upper(),
        )

    def entry(self, mapping_id: str, kind: str = "") -> str:
        """`kind` is "", "_safe" or "_fn"; the suffix always comes last."""
        return f"{self.prefix}map_{mapping_id}{kind}{self.suffix}"

    def rule(self, mapping_id: str, rule_id: str) -> str:
        """Name of a rule function (it lives in its mapping's package)."""
        return f"{self.prefix}fn_{mapping_id}_{rule_id}{self.suffix}"

    def library_call(self, function: str) -> str:
        """How a mapping calls a function of the shared functions package."""
        return f"{self.qualified(self.functions_package)}.{function}"

    def caller_package(self, mapping_id: str) -> str:
        """The package a caller invokes: the index package when there is one."""
        return self.index_package or self.package_for(mapping_id)

    def call_path(self, mapping_id: str, kind: str = "") -> str:
        """Fully qualified entry point, as a caller outside the packages writes it."""
        return f"{self.qualified(self.caller_package(mapping_id))}.{self.entry(mapping_id, kind)}"

    def deploy_order(self, file_names: list[str]) -> list[str]:
        """Artifact file names in the order they must be deployed: the functions
        package (the mappings call it), the mapping packages, then the index package
        (it calls them)."""
        functions = f"{self.functions_package.lower()}.sql"
        index = f"{self.index_package.lower()}.sql" if self.index_package else None
        return sorted(file_names, key=lambda n: (n != functions, n == index, n))
