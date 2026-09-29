"""Names of the generated PL/SQL objects (docs/backends/plsql.md, §Configuration).

One place derives every name from `[target.plsql]`, so the generator, the
package assembly and the integration harness cannot disagree:

    entry points   <fn_prefix>map_<id>[_safe|_fn]<fn_suffix>
    rule functions <fn_prefix>fn_<id>_<rule><fn_suffix>
    packages       [<schema>.]<package>, and [<schema>.]<fn_package> when set

With `fn_package` the rule functions live in that package (always in its spec,
because the main package body calls them); without it they stay in the main
package, package-private unless `export_rule_functions` is set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from compiler.backends.base import CodeGenError

DEFAULT_PACKAGE = "MAPPING_RULES"

_PREFIX = re.compile(r"([A-Za-z][A-Za-z0-9_$#]*)?")
_SUFFIX = re.compile(r"[A-Za-z0-9_$#]*")
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_$#]*")


def _checked(key: str, value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise CodeGenError(
            f"[target.plsql] {key} = {value!r} is not a valid Oracle identifier part "
            "(letters, digits, _, $, #; names start with a letter)"
        )
    return value


@dataclass(frozen=True)
class PlsqlNaming:
    package: str = DEFAULT_PACKAGE
    schema: str | None = None
    fn_package: str | None = None
    prefix: str = ""
    suffix: str = ""

    @staticmethod
    def from_config(config: dict[str, Any]) -> PlsqlNaming:
        schema = config.get("schema")
        fn_package = config.get("fn_package")
        return PlsqlNaming(
            package=_checked("package", config.get("package", DEFAULT_PACKAGE), _NAME),
            schema=None if schema is None else _checked("schema", schema, _NAME),
            fn_package=None if fn_package is None else _checked("fn_package", fn_package, _NAME),
            prefix=_checked("fn_prefix", config.get("fn_prefix", ""), _PREFIX),
            suffix=_checked("fn_suffix", config.get("fn_suffix", ""), _SUFFIX),
        )

    def qualified(self, package: str) -> str:
        """`SCHEMA.package`, or just `package` without a schema."""
        return f"{self.schema}.{package}" if self.schema else package

    def entry(self, mapping_id: str, kind: str = "") -> str:
        """`kind` is "", "_safe" or "_fn"; the suffix always comes last."""
        return f"{self.prefix}map_{mapping_id}{kind}{self.suffix}"

    def rule(self, mapping_id: str, rule_id: str) -> str:
        """Declaration name of a rule function."""
        return f"{self.prefix}fn_{mapping_id}_{rule_id}{self.suffix}"

    def rule_call(self, mapping_id: str, rule_id: str) -> str:
        """How the main package calls a rule function."""
        name = self.rule(mapping_id, rule_id)
        return f"{self.fn_package}.{name}" if self.fn_package else name

    def call_path(self, mapping_id: str, kind: str = "") -> str:
        """Fully qualified entry point, as a caller outside the package writes it."""
        return f"{self.qualified(self.package)}.{self.entry(mapping_id, kind)}"
