"""Static Python surface for the DSL type system (docs/ARCHITECTURE.md, §Type system).

Imported by generated stubs (`generated/stubs/*.pyi`), generated dataclasses
(`generated/dataclasses/*.py`), and the generated `__mapping__` stub. Never
executed as part of a compiled mapping — these are IDE/type-checker artifacts
only; the Code Generator maps DSL types to target types independently.
"""

from __future__ import annotations

from datetime import date as date
from datetime import datetime as datetime
from typing import Any, NewType

__all__ = ["number", "date", "datetime", "Null", "JsonObj"]

# DSL `number` (arbitrary-precision decimal semantics, PL/SQL NUMBER) is
# distinct from DSL `int` (Python `int`) and from a plain `float` — kept as
# its own nominal type so a mapping can't silently mix them up.
number = NewType("number", float)

# `date` / `datetime` above re-export the stdlib types as their static shape
# (explicit `as date`/`as datetime` for proper re-export, not shadowing); the
# Code Generator maps them to PL/SQL DATE / TIMESTAMP independently.


class Null:
    """DSL sentinel type for explicit JSON null (§Return semantics).

    Distinct from Python's `None` — usable in annotations as `T | Null` for
    fields that may be *explicitly* emitted as JSON null, as opposed to
    `T | None` which is Python-side optionality resolved by the compiler.
    """


# Opaque fallback for `patternProperties` / other open-ended JSON Schema
# constructs (§Type system). Treated as `Any` by the type checker; structural
# validation is delegated to the post-mapping JSON Schema validator.
JsonObj = Any
