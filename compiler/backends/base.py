"""Target-backend interface (docs/ARCHITECTURE.md, §Compiler components).

The Code Generator is the only target-specific compiler component; every
phase before it (Validator, Scope Resolver, Type Checker, Function Linker,
Loop Fusion Optimizer) is language-agnostic. Only `plsql` ships today, but
the boundary is fixed now because the architecture's `@override(target=...)`
mechanism and the multi-target `[target.<name>]` `mapper.toml` shape already
assume a backend interface exists.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldRule:
    """One compiled field rule, ready for emission (§Rule id generation:
    in bootstrap mode `id` is simply the rule's function/field name)."""

    id: str
    return_type: str  # DSL type name: str | int | number | bool | date | datetime
    body: str  # backend-native function body text, already translated


class CodeGenerator(ABC):
    """One backend implements this per target language."""

    target: str

    @abstractmethod
    def size_string_type(self, max_length: int | None) -> str:
        """Map a DSL `str` field (with optional JSON Schema `maxLength`) to
        this target's native string type."""

    @abstractmethod
    def emit_field_guard(self, rule: FieldRule, out_field: str) -> str:
        """Emit the per-rule call site: invoke the rule, apply the
        skip/null/value emission contract, and accumulate (not raise) on
        failure (§Runtime error semantics)."""

    @abstractmethod
    def emit_loop(self, loop_var: str, source_expr: str, body: str) -> str:
        """Emit a single generated loop over a source array."""

    @abstractmethod
    def emit_procedure_pair(
        self, mapping_id: str, declarations: str, body: str, error_code: int
    ) -> str:
        """Emit the twin `map_<id>` (raises) / `map_<id>_safe` (never
        raises) procedures sharing the same core logic (§Generated artifact,
        §Runtime error semantics)."""
