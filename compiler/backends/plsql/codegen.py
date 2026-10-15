"""PL/SQL Code Generator — bootstrap mode (M2a/M2b).

Emits the twin `map_<id>` / `map_<id>_safe` procedures described in
docs/ARCHITECTURE.md §Generated artifact / §Runtime error semantics.

**Function-calling convention** (locked in after discussion): rule
functions (`def`) are written at the *source* root level in `.map.py`, with
explicit typed parameters — no implicit closure over `root`/`src`/the
enclosing loop variable. A function only ever sees what's passed to it:

    def line_rule(itm: Item) -> Line:
        return Line(LineId=itm.id, LineAmount=itm.price)

    for itm in root.orders.items:
        out.Lines.append(line_rule(itm))

**Standalone, package-assembly-ready functions, namespaced per mapping.**
Each rule function is emitted as its own subprogram, a sibling of
`map_<id>` / `map_<id>_safe` — not nested inside them — and named
`fn_<mapping_id>_<rule_id>`. Rule ids are only unique *within* a mapping, so
the mapping id is the namespace: all mappings of a project share one PL/SQL
package (`[target.plsql] package`), and the prefix keeps their private rule
functions from colliding. `compile_module` returns a `PlsqlUnit` (this
mapping's subprograms, not yet wrapped in any `CREATE`);
`compiler.backends.plsql.package.assemble_package` (called by `PlsqlBackend.assemble`) puts every unit into one
package spec + body, listing `fn_*` in the spec too only when
`[target.plsql] export_rule_functions = true` (§Generated artifact,
"Rule-function visibility") — that only works cleanly if rule functions are
already independent subprograms, not closures nested inside a specific
caller.

**"Omit field" without a shared exception.** A standalone function can't
rely on a `WHEN e_field_omitted THEN` handler declared in some specific
caller's scope (that was M2a's mechanism, viable only because rule
functions were nested inside their one caller). Instead, every rule
function takes a trailing `p_omitted OUT BOOLEAN` parameter: bare `return`
sets it `TRUE` and returns `NULL`; every other path sets it `FALSE`
(defaulted at function entry). The call site checks `p_omitted` after the
call instead of catching a dedicated exception — same three-way emission
contract (§Return semantics), a mechanism that works identically whether
the function ends up nested, standalone, or package-private.

**Composite output values** — `Line(LineId=..., LineAmount=...)` (keyword
construction of a `@dataclass`) has no dedicated AST node; it is an
ordinary `Call` whose `func` name happens to be a locally-declared
dataclass. It is built **in memory**, field by field, directly on a
`JSON_OBJECT_T` via a `.put()` sequence — never round-tripped through
`JSON_OBJECT(...)`/text at all. An earlier version did that text round
trip (`JSON_OBJECT_T(JSON_OBJECT(...))`) and hit two real problems: native
PL/SQL rejects `JSON_OBJECT(...) RETURNING CLOB` (PLS-00684 — that clause
is SQL-context-only), and even the default (VARCHAR2) form caps the whole
serialized value at 4000 bytes for no reason, since `JSON_OBJECT_T.put()`
has no such limit. Supported today only as the direct value of a `return`
or of `out.<field> = ...` / `.append(...)` — not as a nested sub-expression
(`_materialize_dataclass` needs a statement sequence, not a single
expression slot).

**Output arrays** — `out.<Field>.append(<expr>)` is recognized as a
statement (an `Expr` wrapping a `Call` to `<out-attribute-chain>.append`),
not a new grammar construct (`Call`/`Attribute`/`Expr`-statement are all
already unrestricted by the Validator). Every list-typed output field gets
one `JSON_ARRAY_T` accumulator declared at the top of each procedure,
appended to wherever the source `.append()` call appears (including inside
a generated `for`-loop), and `.put()` onto `v_out_obj` once at the end.

**Standing principle: CLOB only at the true boundary.** `p_src`/`p_out`/
`p_err` are CLOB because that's the procedure's external contract
(§Generated artifact) — nothing more. `p_src` is parsed into `v_srcroot`
exactly once, at the top; `v_out_obj`/list accumulators are serialized to
CLOB exactly once, at the bottom (`p_out := v_out_obj.TO_CLOB()`;
`p_err := v_err_arr.to_clob()`). Everything in between — every rule
function, every dataclass construction, every `get_*`/`.put()`/`.append()`
call — stays in native `JSON_OBJECT_T`/`JSON_ARRAY_T` object form. No
intermediate text/CLOB round trip, and no dropping into a SQL-context-only
construct (like `JSON_OBJECT(...)`, which caused the PLS-00684 bug above)
where a native PL/SQL object-method call does the same job without the
context switch. The one narrow, unavoidable exception is the error
payload's *message text* itself (`RAISE_APPLICATION_ERROR` and `p_err` are
inherently text/CLOB by their own nature, not by choice).

(Deferred, not yet needed by any fixture: a mapping whose *root* output is
itself an array rather than an object would need `v_out_obj` to be a
`JSON_ARRAY_T` instead of a `JSON_OBJECT_T` — same principle, just a
different top-level accumulator type. Every fixture so far has an
object-shaped root output.)

Scope of this milestone (documented, not silently assumed):
- `for` loops in the mapping body, and inside rule functions (nested output
  arrays: a local list filled by a loop, dataclass fields that are lists,
  nested dataclasses or calls to other rule functions).
- Loop Fusion runs in the pipeline before this backend: the tree it receives is
  already fused.
- Package assembly (spec/body, `schema`, the index package) lives in `package.py`; names in
  `naming.py`.
- String sizing from JSON Schema `maxLength` is not wired up yet — `str`
  fields/locals default to a generic `VARCHAR2(4000 CHAR)` declaration.
- The RAISE_APPLICATION_ERROR payload is byte-budget-aware (§Runtime error
  semantics + M0.5 spike findings, docs/spike-notes.md).
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from compiler.annotations import AnnotationError, resolve_dsl_type
from compiler.backends.base import CodeGenError, CompiledUnit
from compiler.backends.plsql.builtins import (
    BUILTIN_FUNCTIONS,
    LIBRARY_FUNCTIONS,
    to_number_of_kind,
    to_string_of_kind,
)
from compiler.backends.plsql.naming import PlsqlNaming
from compiler.function_linker import FunctionLinker
from compiler.loop_fusion import (
    NEXT_INDEX,
    _parallel_degree,
    extract_continue_filter,
    lower_filtered_iter,
    wrap_filter,
)
from compiler.loop_iter import LoopIterError, SortSpec, parse_for_iter, parse_for_target
from compiler.validation import SCHEMA_CODE, Validation, schema_hash

# PL/SQL requires a VARCHAR2 *variable* declaration to carry a size (unlike
# a function RETURN type or PARAMETER type, which must NOT — see
# `_DSL_TO_PLSQL_UNCONSTRAINED` below).
_EXPECTED_TO_DECL_TYPE = {
    "VARCHAR2": "VARCHAR2(4000 CHAR)",
    "NUMBER": "NUMBER",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
    "OBJECT": "JSON_OBJECT_T",
    "ARRAY": "JSON_ARRAY_T",
}

# PL/SQL disallows size/scale constraints on a function's RETURN type or on
# a parameter's type (PLS-00263) — both must be declared unconstrained.
_DSL_TO_PLSQL_UNCONSTRAINED = {
    "str": "VARCHAR2",
    "int": "NUMBER",
    "number": "NUMBER",
    "bool": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
}

_GETTER = {
    "VARCHAR2": "get_String",
    "NUMBER": "get_Number",
    "BOOLEAN": "get_Boolean",
    "DATE": "get_Date",
    "TIMESTAMP": "get_Timestamp",
}

_DSL_TO_EXPECTED = {
    "str": "VARCHAR2",
    "int": "NUMBER",
    "number": "NUMBER",
    "bool": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
}

_COMPARE_OPS = {
    ast.Eq: "=",
    ast.NotEq: "<>",
    ast.Lt: "<",
    ast.Gt: ">",
    ast.LtE: "<=",
    ast.GtE: ">=",
}

_BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}

# Per-builtin, per-positional-arg expected PL/SQL scalar kind. `None` means
# "inherit the call's own outer expected type" (e.g. coalesce's branches).
# `concat` is variadic and handled separately (every arg is VARCHAR2).
_BUILTIN_ARG_EXPECTED: dict[str, list[str | None]] = {
    "coalesce": [None, None],
    "round": ["NUMBER", "NUMBER"],
    "trunc": ["NUMBER", "NUMBER"],
    "if_else": ["BOOLEAN", None, None],
    "split_first": ["VARCHAR2", "VARCHAR2"],
    "split_nth": ["VARCHAR2", "VARCHAR2", "NUMBER"],
    "lookup": ["VARCHAR2", "OBJECT", "VARCHAR2"],
    "parse_date": ["VARCHAR2", "VARCHAR2"],
    "count": ["ARRAY"],
    # only reached when the project overrides them: otherwise they are lowered to a loop
    "max": ["ARRAY", "VARCHAR2"],
    "min": ["ARRAY", "VARCHAR2"],
    "sum": ["ARRAY", "VARCHAR2"],
    "avg": ["ARRAY", "VARCHAR2"],
    "replace": ["VARCHAR2", "VARCHAR2", "VARCHAR2"],
    "regexp_replace": ["VARCHAR2", "VARCHAR2", "VARCHAR2"],
    "regexp_group": ["VARCHAR2", "VARCHAR2", "NUMBER"],
    "remove_prefix": ["VARCHAR2", "VARCHAR2"],
    "format_decimal": ["NUMBER", "NUMBER"],
    "to_number": ["VARCHAR2"],
    "to_string": ["NUMBER"],
    "is_empty": [None, "BOOLEAN"],
    "to_utc": ["VARCHAR2", "NUMBER"],
    "rfc3339_normalize": ["VARCHAR2", "NUMBER"],
    "parse_timestamp": ["VARCHAR2", "VARCHAR2"],
    "split_last": ["VARCHAR2", "VARCHAR2"],
    "is_digits": ["VARCHAR2"],
    "days_between": ["VARCHAR2", "VARCHAR2"],
    "add_days": ["VARCHAR2", "NUMBER"],
    "join": ["ARRAY", "VARCHAR2"],
    "upper": ["VARCHAR2"],
    "lower": ["VARCHAR2"],
    "trim": ["VARCHAR2"],
    "length": ["VARCHAR2"],
    "substring": ["VARCHAR2", "NUMBER", "NUMBER"],
    "left": ["VARCHAR2", "NUMBER"],
    "right": ["VARCHAR2", "NUMBER"],
    "pad_left": ["VARCHAR2", "NUMBER", "VARCHAR2"],
    "pad_right": ["VARCHAR2", "NUMBER", "VARCHAR2"],
    "contains": ["VARCHAR2", "VARCHAR2"],
    "starts_with": ["VARCHAR2", "VARCHAR2"],
    "ends_with": ["VARCHAR2", "VARCHAR2"],
    "format_date": ["VARCHAR2", "VARCHAR2"],
    "abs": ["NUMBER"],
    "floor": ["NUMBER"],
    "ceil": ["NUMBER"],
}

# Conservative target for the *entries* JSON, leaving margin under the
# ~1899-byte ceiling observed for `DBMS_UTILITY.FORMAT_ERROR_STACK` against a
# real Oracle 23ai instance (M0.5 spike) — see the comment at `raising_tail`.
_ERROR_PAYLOAD_BYTE_BUDGET = 1800


@dataclass(frozen=True)
class PlsqlSubprogram:
    """One package subprogram: `spec` is the declaration (ends with `;`, as
    it appears in the package spec), `body` the full definition."""

    name: str
    spec: str
    body: str


@dataclass(frozen=True)
class PlsqlUnit(CompiledUnit):
    """One compiled mapping, ready for package assembly."""

    mapping_id: str
    rule_functions: list[PlsqlSubprogram]
    # map_<id>, map_<id>_safe, and map_<id>_fn when a rule declares `@parallel`
    entry_points: list[PlsqlSubprogram]
    # built-ins called in the shared functions package (names, sorted)
    library_functions: list[str] = field(default_factory=list)
    # the mapping checks its input and/or output: its `_safe` has one more OUT parameter, the report
    validated: bool = False

    def to_json(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_json(data: dict) -> PlsqlUnit:
        return PlsqlUnit(
            mapping_id=data["mapping_id"],
            rule_functions=[PlsqlSubprogram(**d) for d in data["rule_functions"]],
            entry_points=[PlsqlSubprogram(**d) for d in data["entry_points"]],
            library_functions=list(data.get("library_functions", [])),
            validated=bool(data.get("validated", False)),
        )


# Oracle identifier limit (12.2+): 128 bytes.
_MAX_IDENTIFIER_BYTES = 128


def _check_identifier(name: str) -> str:
    if len(name.encode()) > _MAX_IDENTIFIER_BYTES:
        raise CodeGenError(
            f"generated identifier '{name}' exceeds Oracle's {_MAX_IDENTIFIER_BYTES}-byte "
            "limit — shorten the mapping id or rule name"
        )
    return name


# the report of the checks of a mapping that validates (shared by its two entry points)
_REPORT_DECLS = [
    "v_report   JSON_ARRAY_T := JSON_ARRAY_T();",
    "v_rejected BOOLEAN := FALSE;",
    "v_schema_failed_input  BOOLEAN := FALSE;",
    "v_schema_failed_output BOOLEAN := FALSE;",
    "PROCEDURE add_failed(p_side IN VARCHAR2, p_code IN VARCHAR2, p_message IN VARCHAR2,"
    " p_action IN VARCHAR2) IS",
    "    v_item JSON_OBJECT_T := JSON_OBJECT_T();",
    "BEGIN",
    "    v_item.put('side', p_side);",
    "    v_item.put('code', p_code);",
    "    v_item.put('message', p_message);",
    "    v_item.put('action', p_action);",
    "    v_report.append(v_item);",
    "    IF p_action = 'reject' THEN v_rejected := TRUE; END IF;",
    "END add_failed;",
]


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


@dataclass(frozen=True)
class _DataclassField:
    name: str
    base_type: str
    nullable: bool


@dataclass(frozen=True)
class _DataclassDef:
    name: str
    fields: list[_DataclassField]


def _collect_dataclasses(tree: ast.Module) -> dict[str, _DataclassDef]:
    registry: dict[str, _DataclassDef] = {}
    for stmt in tree.body:
        if not isinstance(stmt, ast.ClassDef):
            continue
        is_dataclass = any(
            (isinstance(d, ast.Name) and d.id == "dataclass")
            or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
            for d in stmt.decorator_list
        )
        if not is_dataclass:
            continue
        fields: list[_DataclassField] = []
        for body_stmt in stmt.body:
            if isinstance(body_stmt, ast.AnnAssign) and isinstance(body_stmt.target, ast.Name):
                base, nullable = resolve_dsl_type(body_stmt.annotation)
                fields.append(_DataclassField(body_stmt.target.id, base, nullable))
        registry[stmt.name] = _DataclassDef(stmt.name, fields)
    return registry


def _expected_kind(base_type: str) -> str:
    """PL/SQL scalar-getter kind for a DSL base type name, "ARRAY" for
    `list[T]`, or "OBJECT" for anything else (a dataclass, or an unchecked
    schema-derived type)."""
    if base_type.startswith("list["):
        return "ARRAY"
    return _DSL_TO_EXPECTED.get(base_type, "OBJECT")


def _plsql_unconstrained_type(base_type: str) -> str:
    """Unconstrained PL/SQL type for a RETURN clause or parameter."""
    if base_type.startswith("list["):
        return "JSON_ARRAY_T"
    return _DSL_TO_PLSQL_UNCONSTRAINED.get(base_type, "JSON_OBJECT_T")


@dataclass
class _RuleSignature:
    param_names: list[str]
    param_expected: list[str]  # per-param expected kind, for call-site arg translation
    param_plsql_types: list[str]
    return_base_type: str
    return_expected: str
    return_plsql_type: str
    nullable: bool
    # the function calls other rule functions, so it takes the `p__errors` sink where a
    # failed nested member is recorded (the member is left out, the function goes on)
    records_errors: bool = False


# Error sink shared by the rule functions of one entry-point call (§Nested output: error
# isolation). `JSON_OBJECT_T` of `rule id -> cause`; the entry point merges it into `v_errors`.
_ERRORS_PARAM = "p__errors"
_ERRORS_LOCAL = "v_rule_errors"


def _calls_rule_function(fn_def: ast.FunctionDef, rule_names: set[str]) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in rule_names
        for n in ast.walk(fn_def)
    )


def _call_args(sig: _RuleSignature, args: list[str], errors_var: str, omitted_var: str) -> str:
    """Argument list of a rule-function call: values, the error sink when the callee
    takes one, then the `omitted` flag."""
    return ", ".join([*args, *([errors_var] if sig.records_errors else []), omitted_var])


def _record_error(rule_id: str, errors_var: str) -> list[str]:
    """First failure of a rule wins, like the entry point's own `v_errors`."""
    return [
        f"IF NOT {errors_var}.has({_quote(rule_id)}) THEN",
        f"    {errors_var}.put({_quote(rule_id)}, SQLERRM);",
        "END IF;",
    ]


def _isolated_call(rule_id: str, call: str, target: str, omitted: str) -> list[str]:
    """`target := call`, where a failure records the error and marks the member omitted."""
    return [
        "BEGIN",
        f"    {target} := {call};",
        "EXCEPTION",
        "    WHEN OTHERS THEN",
        *_indent(_record_error(rule_id, _ERRORS_PARAM), 2),
        f"        {omitted} := TRUE;",
        "END;",
    ]


def _resolve_signature(fn_def: ast.FunctionDef) -> _RuleSignature:
    if fn_def.returns is None:
        raise CodeGenError(f"function '{fn_def.name}' is missing a return annotation")
    try:
        return_base, nullable = resolve_dsl_type(fn_def.returns)
    except AnnotationError as exc:
        raise CodeGenError(str(exc)) from exc

    param_names: list[str] = []
    param_expected: list[str] = []
    param_plsql_types: list[str] = []
    for a in fn_def.args.args:
        if a.annotation is None:
            raise CodeGenError(f"parameter '{a.arg}' of '{fn_def.name}' has no type annotation")
        try:
            p_base, _p_nullable = resolve_dsl_type(a.annotation)
        except AnnotationError as exc:
            raise CodeGenError(str(exc)) from exc
        param_names.append(a.arg)
        param_expected.append(_expected_kind(p_base))
        param_plsql_types.append(_plsql_unconstrained_type(p_base))

    return _RuleSignature(
        param_names=param_names,
        param_expected=param_expected,
        param_plsql_types=param_plsql_types,
        return_base_type=return_base,
        return_expected=_expected_kind(return_base),
        return_plsql_type=_plsql_unconstrained_type(return_base),
        nullable=nullable,
    )


def _is_next_index(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Assign)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Name)
        and stmt.value.func.id == NEXT_INDEX
    )


def _name_of(node: ast.expr) -> str:
    assert isinstance(node, ast.Name)
    return node.id


def _const_int(node: ast.expr) -> int:
    assert isinstance(node, ast.Constant) and isinstance(node.value, int)
    return node.value


def _counted_indexes(stmts: list[ast.stmt]) -> list[tuple[str, int, int]]:
    """`(index name, start, counter id)` for every `i = __next_index__(...)`
    directly owned by this loop body (nested `for` loops own their own)."""
    found: list[tuple[str, int, int]] = []
    for stmt in stmts:
        if _is_next_index(stmt):
            assert isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call)
            found.append(
                (
                    _name_of(stmt.targets[0]),
                    _const_int(stmt.value.args[0]),
                    _const_int(stmt.value.args[1]),
                )
            )
        elif isinstance(stmt, ast.If):
            found += _counted_indexes(stmt.body)
            found += _counted_indexes(stmt.orelse)
    return found


class _IndexVar(str):
    """A loop's `enumerate()` index variable, kept in the same list as item
    variables (both resolve as `v_<name>`) but never what `src` means."""


class _FlowCtx:
    """Name resolution for the *flowing* module/loop scope: `root`, `src`,
    and loop variables are magic here. No local variables (the Validator
    forbids bare local assignment outside a function body)."""

    def __init__(self, loop_vars: list[str]):
        # Innermost last — used only for `src` (nearest enclosing loop).
        self.loop_vars = loop_vars
        # the variable of an aggregate's comprehension (`x` in `sum(x.v for x in ...)`)
        self.elements: dict[str, str] = {}

    def resolve_name(self, name: str) -> str | None:
        if name in self.elements:
            return self.elements[name]
        if name == "root":
            return "v_srcroot"
        if name == "src":
            items = [v for v in self.loop_vars if not isinstance(v, _IndexVar)]
            if not items:
                raise CodeGenError("`src` used outside a loop")
            return f"v_{items[-1]}"
        if name in self.loop_vars:
            return f"v_{name}"
        return None


class _FnCtx:
    """Name resolution inside a rule-function body: only its own declared
    parameters and locals are visible — no implicit access to `root`/`src`/
    the caller's loop variable (§ module docstring)."""

    def __init__(self, params: list[str], local_prefix: str):
        self.params = set(params)
        self.local_prefix = local_prefix
        self.locals: dict[str, str] = {}
        self.declarations: list[str] = []
        # locals bound from a rule-function call: name -> its `omitted` flag variable
        self.omit_flags: dict[str, str] = {}
        self.counter = itertools.count()  # temp names, loop-index counters
        self.loop_counter: itertools.count = (
            self.counter
        )  # the numbers of the loops of the function
        self.declared_names: set[str] = set()  # locals this code declared itself
        self.elements: dict[str, str] = {}  # as in `_FlowCtx`

    def resolve_name(self, name: str) -> str | None:
        if name in self.elements:
            return self.elements[name]
        if name in self.params:
            return f"p_{name}"
        return None

    def declare(self, decl: str) -> None:
        if decl not in self.declarations:
            self.declarations.append(decl)

    def local_var(self, name: str) -> str:
        return f"v_{self.local_prefix}_{name}"


class _ExprTranslator:
    def __init__(
        self,
        ctx: _FlowCtx | _FnCtx,
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
        function_linker: FunctionLinker,
        fn_name: Callable[[str], str] | None = None,
        library_name: Callable[[str], str | None] | None = None,
    ):
        self.ctx = ctx
        self.rule_signatures = rule_signatures
        self.dataclasses = dataclasses
        self.function_linker = function_linker
        self.fn_name = fn_name
        # a built-in living in the functions package -> its call name (None = inline)
        self.library_name = library_name

    def translate(self, node: ast.expr, expected: str | None) -> str:
        method = getattr(self, f"_t_{type(node).__name__}", None)
        if method is None:
            raise CodeGenError(f"unsupported expression: {type(node).__name__}")
        return method(node, expected)

    def _t_Constant(self, node: ast.Constant, expected: str | None) -> str:
        v = node.value
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, str):
            return _quote(v)
        return str(v)

    def _t_Dict(self, node: ast.Dict, expected: str | None) -> str:
        """A constant dict literal (e.g. an inlined `lookup` table) as a
        `JSON_OBJECT_T` built from its JSON text. Constants only: str keys,
        JSON-scalar values."""
        table: dict[str, object] = {}
        for k, v in zip(node.keys, node.values, strict=True):
            if not (
                isinstance(k, ast.Constant)
                and isinstance(k.value, str)
                and isinstance(v, ast.Constant)
                and isinstance(v.value, (str, int, float, bool, type(None)))
            ):
                raise CodeGenError("dict literals must map string constants to scalar constants")
            table[k.value] = v.value
        return f"JSON_OBJECT_T({_quote(json.dumps(table, ensure_ascii=False))})"

    def _t_Name(self, node: ast.Name, expected: str | None) -> str:
        name = node.id
        if name == "Null":
            return "NULL"
        resolved = self.ctx.resolve_name(name)
        if resolved is not None:
            return resolved
        if isinstance(self.ctx, _FnCtx) and name in self.ctx.locals:
            return f"v_{self.ctx.local_prefix}_{name}"
        raise CodeGenError(f"unresolved name '{name}'")

    def _t_Attribute(self, node: ast.expr, expected: str | None) -> str:
        base, segments = _access_chain(node)
        if not isinstance(base, ast.Name):
            raise CodeGenError("unsupported attribute chain base")
        code = self.translate(base, None)
        # each step reads an object (next is a field) or an array (next is a position)
        for seg, following in zip(segments, segments[1:], strict=False):
            code = _step(code, seg, "Array" if isinstance(following, int) else "Object")
        last = _segment(segments[-1])
        if expected == "OBJECT":
            return _step(code, segments[-1], "Object")
        if expected == "ARRAY":
            return _step(code, segments[-1], "Array")
        return f"{code}.{_GETTER.get(expected or '', 'get_String')}({last})"

    _t_Subscript = _t_Attribute

    def _t_BinOp(self, node: ast.BinOp, expected: str | None) -> str:
        op_type = type(node.op)
        left = self.translate(node.left, "NUMBER")
        right = self.translate(node.right, "NUMBER")
        if op_type in _BINOPS:
            return f"({left} {_BINOPS[op_type]} {right})"
        if op_type is ast.Div:
            return f"({left} / {right})"
        if op_type is ast.FloorDiv:
            return f"TRUNC({left} / {right})"
        if op_type is ast.Mod:
            return f"MOD({left}, {right})"
        raise CodeGenError(f"unsupported operator: {op_type.__name__}")

    def _t_Compare(self, node: ast.Compare, expected: str | None) -> str:
        if len(node.ops) != 1:
            raise CodeGenError("chained comparisons are not supported")
        op = node.ops[0]
        if isinstance(op, ast.In | ast.NotIn):
            return self._membership(node, isinstance(op, ast.NotIn))
        if type(op) not in _COMPARE_OPS:
            raise CodeGenError(f"unsupported comparison operator: {type(op).__name__}")
        # `x == None` / `x != None` must be IS [NOT] NULL: in SQL `x = NULL` is
        # never true, so a literal translation would make the test always NULL.
        if isinstance(op, (ast.Eq, ast.NotEq)):
            left_node, right_node = node.left, node.comparators[0]
            for a, b in ((left_node, right_node), (right_node, left_node)):
                if isinstance(b, ast.Constant) and b.value is None:
                    is_null = "IS NULL" if isinstance(op, ast.Eq) else "IS NOT NULL"
                    return f"({self.translate(a, None)} {is_null})"
        operand_expected = "VARCHAR2"
        for side in (node.left, node.comparators[0]):
            if isinstance(side, ast.Constant) and isinstance(side.value, bool):
                operand_expected = "BOOLEAN"
            elif (
                isinstance(side, ast.Constant)
                and isinstance(side.value, (int, float))
                and not isinstance(side.value, bool)
            ):
                operand_expected = "NUMBER"
        left = self.translate(node.left, operand_expected)
        right = self.translate(node.comparators[0], operand_expected)
        return f"({left} {_COMPARE_OPS[type(op)]} {right})"

    def _membership(self, node: ast.Compare, negated: bool) -> str:
        """`x in ("A", "B")` / `x not in (...)` with a literal list. A missing `x` is in nothing, as in
        Python (SQL's `NULL IN (...)` is NULL, which `NOT` would keep NULL)."""
        values = node.comparators[0]
        if not isinstance(values, ast.Tuple | ast.List | ast.Set) or not all(
            isinstance(v, ast.Constant) and not isinstance(v.value, type(None)) for v in values.elts
        ):
            raise CodeGenError("`in` needs a literal list of texts or numbers: x in ('A', 'B')")
        constants = [v.value for v in values.elts if isinstance(v, ast.Constant)]
        numeric = all(isinstance(c, int | float) and not isinstance(c, bool) for c in constants)
        if not numeric and not all(isinstance(c, str) for c in constants):
            raise CodeGenError("`in` takes a list of texts or a list of numbers, not a mix")
        kind = "NUMBER" if numeric else "VARCHAR2"
        left = self.translate(node.left, kind)
        listed = ", ".join(self.translate(v, kind) for v in values.elts)
        test = f"COALESCE({left} IN ({listed}), FALSE)"
        return f"(NOT {test})" if negated else f"({test})"

    def condition(self, node: ast.expr) -> str:
        """A condition (`if`, `guard`, `filter`, `and` / `or` / `not`, `if_else`'s first
        argument) with Python's truthiness (docs/ARCHITECTURE.md, §Truthiness): a missing
        value, `null`, `false`, `0`, `""`, `[]` and `{}` are false, anything else is true.
        Comparisons and boolean operators are conditions already; any other value is
        tested by its type, or, for a value read from the source document, at runtime."""
        if isinstance(node, ast.BoolOp):
            joiner = " AND " if isinstance(node.op, ast.And) else " OR "
            return "(" + joiner.join(self.condition(v) for v in node.values) + ")"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"(NOT {self.condition(node.operand)})"
        if isinstance(node, ast.Compare):
            return self.translate(node, "BOOLEAN")
        if isinstance(node, ast.Constant):
            return "TRUE" if node.value else "FALSE"
        if isinstance(node, ast.Attribute | ast.Subscript):
            return self._truthy_of_document_value(node)
        if isinstance(node, ast.IfExp):
            body, orelse = self.condition(node.body), self.condition(node.orelse)
            return f"(CASE WHEN {self.condition(node.test)} THEN {body} ELSE {orelse} END)"
        kind = infer_type(node, self.ctx) if isinstance(self.ctx, _FnCtx) else "BOOLEAN"
        value = self.translate(node, kind)
        if kind == "BOOLEAN":
            return f"COALESCE({value}, FALSE)"
        if kind == "NUMBER":
            return f"(COALESCE({value}, 0) <> 0)"
        if kind in ("ARRAY", "OBJECT"):
            return f"({value} IS NOT NULL AND {value}.get_size > 0)"
        return f"({value} IS NOT NULL)"  # text ('' is NULL in Oracle), dates

    def _document_element(self, node: ast.expr) -> str:
        """`root.a.b` as the JSON element itself, whatever its type (a value that goes to a
        shared function which looks at what it is)."""
        base, segments = _access_chain(node)
        code = self.translate(base, None)
        for seg, following in zip(segments, segments[1:], strict=False):
            code = _step(code, seg, "Array" if isinstance(following, int) else "Object")
        return f"{code}.get({_segment(segments[-1])})"

    def _truthy_of_document_value(self, node: ast.expr) -> str:
        """`root.a.b` tested without knowing its JSON type: the element goes to the shared
        `truthy` function, which looks at what it is."""
        element = self._document_element(node)
        library = self.library_name("truthy") if self.library_name else None
        if library is None:
            raise CodeGenError("the shared functions package is not available for `truthy`")
        return f"{library}({element})"

    def _convert(self, name: str, arg: ast.expr) -> str:
        """`to_string` / `to_number` of one argument, the same whatever its JSON or PL/SQL type
        (docs/ARCHITECTURE.md, §Built-in functions): a value read from the document goes, as the
        element, to the shared function that looks at what it is; a typed value is converted by
        its type."""
        if isinstance(arg, ast.Attribute | ast.Subscript):
            library = self.library_name(name) if self.library_name else None
            if library is None:
                raise CodeGenError(f"the shared functions package is not available for `{name}`")
            return f"{library}({self._document_element(arg)})"
        kind = infer_type(arg, self.ctx) if isinstance(self.ctx, _FnCtx) else "VARCHAR2"
        if isinstance(arg, ast.Constant) and arg.value is None:
            return "NULL"
        render = to_string_of_kind if name == "to_string" else to_number_of_kind
        try:
            return render(kind, self.translate(arg, kind))
        except ValueError as exc:
            raise CodeGenError(f"{name}(): {exc}") from exc

    def _is_empty(self, args: list[ast.expr]) -> str:
        """`is_empty(value [, zero_is_empty])` by what the value is: a value read from the document
        goes, as the element, to the shared function that looks at it; a typed one is tested by its
        type (an empty text is NULL in Oracle)."""
        zero = self.translate(args[1], "BOOLEAN") if len(args) > 1 else "FALSE"
        arg = args[0]
        if isinstance(arg, ast.Attribute | ast.Subscript):
            library = self.library_name("is_empty") if self.library_name else None
            if library is None:
                raise CodeGenError("the shared functions package is not available for `is_empty`")
            return f"{library}({self._document_element(arg)}, {zero})"
        if isinstance(arg, ast.Constant) and arg.value is None:
            return "TRUE"
        kind = infer_type(arg, self.ctx) if isinstance(self.ctx, _FnCtx) else "VARCHAR2"
        value = self.translate(arg, kind)
        if kind == "NUMBER":
            return f"({value} IS NULL OR ({zero} AND {value} = 0))"
        return f"({value} IS NULL)"

    def _t_BoolOp(self, node: ast.BoolOp, expected: str | None) -> str:
        return self.condition(node)

    def _t_UnaryOp(self, node: ast.UnaryOp, expected: str | None) -> str:
        if not isinstance(node.op, ast.Not):
            raise CodeGenError("unsupported unary operator")
        return self.condition(node)

    def _t_IfExp(self, node: ast.IfExp, expected: str | None) -> str:
        test = self.condition(node.test)
        body = self.translate(node.body, expected)
        orelse = self.translate(node.orelse, expected)
        return f"(CASE WHEN {test} THEN {body} ELSE {orelse} END)"

    def _t_Call(self, node: ast.Call, expected: str | None) -> str:
        if not isinstance(node.func, ast.Name):
            raise CodeGenError("only direct function calls are supported")
        name = node.func.id

        if name in self.dataclasses:
            raise CodeGenError(
                f"'{name}(...)' dataclass construction is only supported as a direct "
                "`return` value or `out.<field> = ...` / `.append(...)` argument "
                "(§module docstring) — it cannot be used as a nested sub-expression"
            )

        if name in self.rule_signatures:
            raise CodeGenError(
                f"'{name}' returns a value AND an omitted-flag — call it via the "
                "statement-level helper, not as a nested expression (M2b limitation)"
            )

        impl = self.function_linker.resolve(name)
        if name in ("to_string", "to_number") and len(node.args) == 1:
            return self._convert(name, node.args[0])
        if name == "is_empty" and 1 <= len(node.args) <= 2:
            return self._is_empty(node.args)
        if name == "if_else" and len(node.args) == 3:
            test = self.condition(node.args[0])
            arms = [self.translate(a, expected) for a in node.args[1:]]
            return impl.render("plsql", [test, *arms])
        if name == "concat":
            arg_exprs = [self.translate(a, "VARCHAR2") for a in node.args]
        else:
            per_arg_expected = _BUILTIN_ARG_EXPECTED.get(name)
            arg_exprs = [
                self.translate(
                    a,
                    (per_arg_expected[i] if per_arg_expected and per_arg_expected[i] else expected),
                )
                for i, a in enumerate(node.args)
            ]
        library = self.library_name(name) if self.library_name else None
        if library is not None and impl is BUILTIN_FUNCTIONS.get(name):
            return f"{library}({', '.join(arg_exprs)})"
        return impl.render("plsql", arg_exprs)


def _is_dataclass_construction(node: ast.expr, dataclasses: dict[str, _DataclassDef]) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in dataclasses
    )


def _materialize_dataclass(
    call: ast.Call,
    translator: _ExprTranslator,
    tmp_var: str,
    ctx: _FnCtx | None = None,
    loop_counter: itertools.count | None = None,
    declarations: list[str] | None = None,
) -> list[str]:
    """Build a dataclass value **in memory**, field by field, into
    `tmp_var` — no text round-trip through `JSON_OBJECT()`/CLOB/VARCHAR2 at
    all, so no 4000-byte ceiling and no PLS-00684 (native PL/SQL rejects
    `JSON_OBJECT(...) RETURNING CLOB` — SQL-context-only, verified against a
    live Oracle 23ai instance). `JSON_OBJECT_T.put()` has no size limit.

    Inside a rule function (`ctx` given) a field value may also be a list
    local, a nested dataclass construction, a call to another rule function
    (omitted -> the key is left out), or a local bound from such a call —
    that is how nested output objects/arrays are composed. At flow level
    (`ctx` is None) only plain expressions are accepted."""
    assert isinstance(call.func, ast.Name)
    name = call.func.id
    cls = translator.dataclasses[name]
    if call.args:
        raise CodeGenError(f"'{name}(...)' construction requires keyword arguments")
    field_by_name = {f.name: f for f in cls.fields}
    lines = [f"{tmp_var} := JSON_OBJECT_T();"]
    for kw in call.keywords:
        if kw.arg is None:
            raise CodeGenError(f"'**kwargs' is not supported in '{name}(...)' construction")
        field_def = field_by_name.get(kw.arg)
        if field_def is None:
            raise CodeGenError(f"'{name}' has no field '{kw.arg}'")
        expected = _expected_kind(field_def.base_type)
        key = _quote(kw.arg)
        if ctx is None or loop_counter is None:
            value_expr = translator.translate(kw.value, expected)
            if _is_explicit_null(kw.value):
                lines.append(f"{tmp_var}.put({key}, {_TYPED_NULL});")
            else:
                lines.extend(
                    _write_unless_null(
                        value_expr, expected if declarations is not None else None,
                        lambda e, k=key: f"{tmp_var}.put({k}, {e});",
                        declarations.append if declarations is not None else (lambda d: None),
                        f"{tmp_var.removeprefix('v_')}_{kw.arg}",
                    )
                )  # fmt: skip
        else:
            lines.extend(
                _emit_value(
                    kw.value,
                    ctx,
                    translator,
                    loop_counter,
                    lambda e, k=key: f"{tmp_var}.put({k}, {e});",
                    expected,
                )
            )
    return lines


def _emit_value(
    value: ast.expr,
    ctx: _FnCtx,
    translator: _ExprTranslator,
    loop_counter: itertools.count,
    sink: Callable[[str], str],
    expected: str | None,
) -> list[str]:
    """Emit the statements delivering `value` to `sink` (a `.put(...)` /
    `.append(...)` template) inside a rule function."""
    # a call to another rule function: value + omitted flag
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in translator.rule_signatures
    ):
        if translator.fn_name is None:
            raise CodeGenError("rule-function calls need a function-name resolver")
        rule = value.func.id
        sig = translator.rule_signatures[rule]
        if len(value.args) != len(sig.param_names):
            raise CodeGenError(
                f"'{rule}' takes {len(sig.param_names)} argument(s), got {len(value.args)}"
            )
        n = next(ctx.counter)
        res, om = f"v_{ctx.local_prefix}__rc{n}", f"v_{ctx.local_prefix}__ro{n}"
        ctx.declare(f"{res} {_decl_type(sig.return_expected)};")
        ctx.declare(f"{om} BOOLEAN;")
        args = [translator.translate(a, sig.param_expected[i]) for i, a in enumerate(value.args)]
        call = f"{translator.fn_name(rule)}({_call_args(sig, args, _ERRORS_PARAM, om)})"
        return [
            *_isolated_call(rule, call, res, om),
            f"IF NOT {om} THEN",
            f"    {sink(res)}",
            "END IF;",
        ]
    if _is_dataclass_construction(value, translator.dataclasses):
        assert isinstance(value, ast.Call)
        n = next(ctx.counter)
        tmp = f"v_{ctx.local_prefix}__dc{n}"
        ctx.declare(f"{tmp} JSON_OBJECT_T;")
        return [
            *_materialize_dataclass(value, translator, tmp, ctx, loop_counter),
            sink(tmp),
        ]
    if isinstance(value, ast.Name) and value.id in ctx.locals:
        var = ctx.local_var(value.id)
        if value.id in ctx.omit_flags:
            return [f"IF NOT {ctx.omit_flags[value.id]} THEN", f"    {sink(var)}", "END IF;"]
        if ctx.locals[value.id] in ("ARRAY", "OBJECT"):
            return [sink(var)]
    if _is_explicit_null(value):
        return [sink(_TYPED_NULL)]
    kind = expected or infer_type(value, ctx)
    return _write_unless_null(
        translator.translate(value, kind), kind, sink, ctx.declare,
        f"{ctx.local_prefix}__v{next(ctx.counter)}",
    )  # fmt: skip


_AGGREGATE_FUNCS = {"max", "min", "sum", "avg", "join"}

_EXPECTED_TO_JSON_ELEMENT_EXTRACTOR = {
    "VARCHAR2": "to_string",
    "NUMBER": "to_number",
    "BOOLEAN": "to_boolean",
    "DATE": "to_date",
    "TIMESTAMP": "to_timestamp",
}


# `put(key, NULL)` is ambiguous to PL/SQL (PLS-00307): an explicit null is a typed one
_TYPED_NULL = "CAST(NULL AS NUMBER)"
_SCALAR_KINDS = ("VARCHAR2", "NUMBER", "BOOLEAN", "DATE", "TIMESTAMP")


def _is_explicit_null(node: ast.expr) -> bool:
    """`Null`: the explicit null, written as a null (a `None` writes nothing)."""
    return isinstance(node, ast.Name) and node.id == "Null"


def _write_unless_null(
    value_expr: str,
    kind: str | None,
    sink: Callable[[str], str],
    declare: Callable[[str], None],
    name: str,
) -> list[str]:
    """A plain value reaches the output only if it is not NULL (a missing value writes nothing).
    A scalar is computed once into a local; anything else is tested where it stands."""
    if kind not in _SCALAR_KINDS:
        return [f"IF {value_expr} IS NOT NULL THEN", f"    {sink(value_expr)}", "END IF;"]
    var = f"v_val_{name}"
    declare(f"{var} {_decl_type(kind)};")
    return [f"{var} := {value_expr};", f"IF {var} IS NOT NULL THEN", f"    {sink(var)}", "END IF;"]


def _is_aggregate_call(node: ast.expr, linker: FunctionLinker) -> bool:
    """A `max` / `min` / `sum` / `avg` / `join` call, or a `count` over a comprehension, that the backend
    lowers to a loop: not one the project overrides (that one is an expression, its
    `@override(plsql=...)` template)."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and (
            node.func.id in _AGGREGATE_FUNCS
            or (
                node.func.id in ("count", "any", "all")
                and len(node.args) == 1
                and isinstance(node.args[0], ast.GeneratorExp)
            )
        )
        and not linker.overrides(node.func.id)
    )


def _materialize_comprehension_aggregate(
    call: ast.Call,
    translator: _ExprTranslator,
    tmp_var: str,
    return_expected: str,
    agg_idx: int,
    declarations: list[str],
) -> list[str]:
    """`sum(expr for x in list if cond)` (and `max`, `min`, `avg`, `count`): one loop over the
    list, the value computed for each element that passes the condition. A missing value is
    skipped, as SQL does; nothing left gives 0 for `sum` and `count`, NULL for the others."""
    assert isinstance(call.func, ast.Name)
    fname = call.func.id
    gen_exp = call.args[0]
    assert isinstance(gen_exp, ast.GeneratorExp)
    if fname == "join" and len(call.args) == 1:
        call = ast.Call(func=call.func, args=[gen_exp, ast.Constant(value="")], keywords=[])
    if len(call.args) != (2 if fname == "join" else 1) or call.keywords:
        raise CodeGenError(
            f"{fname}(... for ... in ...) takes the comprehension"
            + (" and the separator" if fname == "join" else " alone")
        )
    if len(gen_exp.generators) != 1 or gen_exp.generators[0].is_async:
        raise CodeGenError(f"{fname}(...) takes one `for` and optional `if`s")
    gen = gen_exp.generators[0]
    if not isinstance(gen.target, ast.Name):
        raise CodeGenError(f"{fname}(...): the `for` variable must be a plain name")
    ctx = translator.ctx
    if gen.target.id in ctx.elements:
        raise CodeGenError(
            f"{fname}(...): '{gen.target.id}' is already the variable of an aggregate"
        )

    arr_var = f"v_aggarr_{agg_idx}"
    k_var = f"v_aggk_{agg_idx}"
    item_var = f"v_aggel_{agg_idx}"
    acc_var = f"v_aggacc_{agg_idx}"
    val_var = f"v_aggval_{agg_idx}"
    n_var = f"v_aggn_{agg_idx}"
    array_expr = translator.translate(gen.iter, "ARRAY")
    separator = translator.translate(call.args[1], "VARCHAR2") if fname == "join" else ""
    # an aggregate in the condition or in the value is computed inside this loop, for each element:
    # the condition's before the test, the value's once the element has passed it
    cond_lines: list[str] = []
    value_lines: list[str] = []
    ctx.elements[gen.target.id] = item_var
    try:
        nested = _nested_hoister(translator, cond_lines)
        conditions = [translator.condition(nested.visit(copy.deepcopy(c))) for c in gen.ifs]
        value_type = (
            "VARCHAR2"
            if fname == "join"
            else "NUMBER"
            if fname in ("sum", "avg") or return_expected not in _EXPECTED_TO_DECL_TYPE
            else return_expected
        )
        elt = copy.deepcopy(gen_exp.elt)
        if fname in ("any", "all"):
            tested = _nested_hoister(translator, value_lines).visit(elt)
            value = translator.condition(tested)
        elif fname != "count":
            elt = _nested_hoister(translator, value_lines).visit(elt)
            value = translator.translate(elt, value_type)
        else:
            value = ""
    finally:
        del ctx.elements[gen.target.id]

    declarations.extend([f"{arr_var} JSON_ARRAY_T;", f"{item_var} JSON_OBJECT_T;"])
    if fname in ("any", "all"):
        # true as soon as one element passes (`any`), false as soon as one fails (`all`): the loop
        # stops there. A missing value is false.
        found = fname == "any"
        test = value if found else f"NOT COALESCE({value}, FALSE)"
        hit = [f"{tmp_var} := {'TRUE' if found else 'FALSE'};", "EXIT;"]
        inner = [*value_lines, f"IF {test} THEN", *_indent(hit), "END IF;"]
        if conditions:
            inner = [f"IF {' AND '.join(conditions)} THEN", *_indent(inner), "END IF;"]
        loop = [
            f"{item_var} := TREAT({arr_var}.get({k_var}) AS JSON_OBJECT_T);",
            *cond_lines,
            *inner,
        ]
        return [
            f"{arr_var} := {array_expr};",
            f"{tmp_var} := {'FALSE' if found else 'TRUE'};",
            f"IF {arr_var} IS NOT NULL THEN",
            f"    FOR {k_var} IN 0 .. {arr_var}.get_size - 1 LOOP",
            *_indent(loop, 2),
            "    END LOOP;",
            "END IF;",
        ]
    if fname == "count":
        declarations.append(f"{n_var} NUMBER;")
        init, step = [f"{n_var} := 0;"], [f"{n_var} := {n_var} + 1;"]
        done = [f"{tmp_var} := {n_var};"]
    else:
        decl = _decl_type(value_type)
        declarations.extend([f"{val_var} {decl};"])
        if fname == "join":
            declarations.append(f"{acc_var} VARCHAR2(32767);")
            init = [f"{acc_var} := NULL;"]
            step = [
                f"IF {acc_var} IS NULL THEN {acc_var} := {val_var}; "
                f"ELSE {acc_var} := {acc_var} || {separator} || {val_var}; END IF;"
            ]
            done = [f"{tmp_var} := {acc_var};"]
        elif fname in ("sum", "avg"):
            declarations.extend([f"{acc_var} NUMBER;", f"{n_var} NUMBER;"])
            init = [f"{acc_var} := 0;", f"{n_var} := 0;"]
            step = [f"{acc_var} := {acc_var} + {val_var};", f"{n_var} := {n_var} + 1;"]
            done = (
                [f"{tmp_var} := {acc_var};"]
                if fname == "sum"
                else [f"IF {n_var} > 0 THEN {tmp_var} := {acc_var} / {n_var}; END IF;"]
            )
        else:
            declarations.append(f"{acc_var} {decl};")
            op = ">" if fname == "max" else "<"
            init = [f"{acc_var} := NULL;"]
            step = [
                f"IF {acc_var} IS NULL OR {val_var} {op} {acc_var} THEN {acc_var} := {val_var}; END IF;"
            ]
            done = [f"{tmp_var} := {acc_var};"]
    # the condition first: the value of an element left out is never computed
    inner = [*step]
    if fname != "count":
        inner = [
            *value_lines,
            f"{val_var} := {value};",
            f"IF {val_var} IS NOT NULL THEN",
            *_indent(step),
            "END IF;",
        ]
    if conditions:
        inner = [f"IF {' AND '.join(conditions)} THEN", *_indent(inner), "END IF;"]
    loop = [f"{item_var} := TREAT({arr_var}.get({k_var}) AS JSON_OBJECT_T);", *cond_lines, *inner]
    return [
        f"{arr_var} := {array_expr};",
        *init,
        f"IF {arr_var} IS NOT NULL THEN",
        f"    FOR {k_var} IN 0 .. {arr_var}.get_size - 1 LOOP",
        *_indent(loop, 2),
        "    END LOOP;",
        "END IF;",
        *done,
    ]


def _materialize_aggregate(
    call: ast.Call,
    translator: _ExprTranslator,
    tmp_var: str,
    return_expected: str,
    agg_idx: int,
    declarations: list[str],
) -> list[str]:
    """`max`/`min`/`sum`/`avg` over `(array, "field")` — like dataclass
    construction, this needs a native PL/SQL loop (an accumulator), not a
    single-expression template, so it can only appear as a direct `return`
    value or `out.<field> = ...` / `.append(...)` argument. `max`/`min`
    compare via `JSON_ELEMENT_T.compare_to()` (type-agnostic — same
    mechanism as the `sorted()` lowering) so they work for numbers,
    strings, or dates without knowing the field's type ahead of time;
    `sum`/`avg` accumulate as NUMBER directly. Appends any new local
    declarations the loop needs to `declarations` (caller owns where
    those get emitted — a function's declare section, or a `DECLARE`
    block around a guarded `out` write)."""
    assert isinstance(call.func, ast.Name)
    fname = call.func.id
    if call.args and isinstance(call.args[0], ast.GeneratorExp):
        return _materialize_comprehension_aggregate(
            call, translator, tmp_var, return_expected, agg_idx, declarations
        )
    if fname == "join" and len(call.args) == 1:  # no separator: the texts one after the other
        call = ast.Call(func=call.func, args=[call.args[0], ast.Constant(value="")], keywords=[])
    if len(call.args) != 2:
        raise CodeGenError(f"{fname}(...) requires exactly 2 arguments: (list, field_name)")
    if fname == "join":  # the texts of a list
        arr_var, k_var, acc_var = (
            f"v_aggarr_{agg_idx}",
            f"v_aggk_{agg_idx}",
            f"v_aggacc_{agg_idx}",
        )
        val_var = f"v_aggval_{agg_idx}"
        declarations.extend(
            [
                f"{arr_var} JSON_ARRAY_T;",
                f"{acc_var} VARCHAR2(32767);",
                f"{val_var} VARCHAR2(32767);",
            ]
        )
        return [
            f"{arr_var} := {translator.translate(call.args[0], 'ARRAY')};",
            f"{acc_var} := NULL;",
            f"IF {arr_var} IS NOT NULL THEN",
            f"    FOR {k_var} IN 0 .. {arr_var}.get_size - 1 LOOP",
            f"        {val_var} := {arr_var}.get_String({k_var});",
            f"        IF {val_var} IS NOT NULL THEN",
            f"            IF {acc_var} IS NULL THEN {acc_var} := {val_var}; "
            f"ELSE {acc_var} := {acc_var} || {translator.translate(call.args[1], 'VARCHAR2')} "
            f"|| {val_var}; END IF;",
            "        END IF;",
            "    END LOOP;",
            "END IF;",
            f"{tmp_var} := {acc_var};",
        ]
    field_node = call.args[1]
    if not (isinstance(field_node, ast.Constant) and isinstance(field_node.value, str)):
        raise CodeGenError(f"{fname}(...)'s second argument must be a string literal field name")
    # `sum(list, "f")` is `sum(e.f for e in list)`: one lowering, the same rules for a missing
    # list, a missing value and an empty set
    element = ast.Name(id="_e", ctx=ast.Load())
    comprehension = ast.GeneratorExp(
        elt=ast.Attribute(value=element, attr=field_node.value, ctx=ast.Load()),
        generators=[
            ast.comprehension(
                target=ast.Name(id="_e", ctx=ast.Store()), iter=call.args[0], ifs=[], is_async=0
            )
        ],
    )
    return _materialize_comprehension_aggregate(
        ast.Call(func=call.func, args=[comprehension], keywords=[]),
        translator,
        tmp_var,
        return_expected,
        agg_idx,
        declarations,
    )


def _access_chain(node: ast.expr) -> tuple[ast.expr, list[str | int]]:
    """`root.a.list[0].b` -> (`root`, ["a", "list", 0, "b"]): fields by name, array
    elements by a constant position."""
    segments: list[str | int] = []
    cur = node
    while True:
        if isinstance(cur, ast.Attribute):
            segments.append(cur.attr)
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            index = cur.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, str):
                segments.append(index.value)  # a field named like a keyword: x["return"]
            elif isinstance(index, ast.Constant) and type(index.value) is int and index.value >= 0:
                segments.append(index.value)
            else:
                raise CodeGenError("an array element is read by a constant position: x[0]")
            cur = cur.value
        else:
            break
    segments.reverse()
    return cur, segments


def _segment(seg: str | int) -> str:
    return str(seg) if isinstance(seg, int) else _quote(seg)


def _step(code: str, seg: str | int, kind: str) -> str:
    """One step down a JSON path, to an `Object` or an `Array`. A field of a `JSON_OBJECT_T`
    has `get_Object` / `get_Array`; a `JSON_ARRAY_T` has neither (only `get(pos)`, an element of
    any type), so an element of an array is read with `get` and `TREAT`ed to what it is."""
    if isinstance(seg, int):
        return f"TREAT({code}.get({seg}) AS JSON_{kind.upper()}_T)"
    return f"{code}.get_{kind}({_segment(seg)})"


def infer_type(node: ast.expr, ctx: _FnCtx) -> str:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "BOOLEAN"
        if isinstance(node.value, (int, float)):
            return "NUMBER"
        return "VARCHAR2"
    if isinstance(node, ast.BinOp):
        return "NUMBER"
    if isinstance(node, ast.Dict):
        return "OBJECT"
    if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
        return "BOOLEAN"
    if isinstance(node, ast.IfExp):
        return infer_type(node.body, ctx)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fname = node.func.id
        if fname == "coalesce":
            return infer_type(node.args[0], ctx)
        if fname == "if_else":
            return infer_type(node.args[1], ctx)
        if fname in (
            "round",
            "trunc",
            "to_number",
            "length",
            "abs",
            "floor",
            "ceil",
            "days_between",
        ):
            return "NUMBER"
        if fname in ("is_empty", "contains", "starts_with", "ends_with", "is_digits"):
            return "BOOLEAN"
        if fname == "parse_date":
            return "DATE"
        if fname in ("concat", "split_first", "split_nth", "lookup"):
            return "VARCHAR2"
        if fname in ("any", "all"):
            return "BOOLEAN"
        if fname in ("max", "min", "sum", "avg", "count"):
            # Best-effort default: max/min could in principle key on a
            # str/date field, but without schema info to check the field's
            # actual type, NUMBER is the common case.
            return "NUMBER"
    if isinstance(node, ast.Name) and node.id in ctx.locals:
        return ctx.locals[node.id]
    return "VARCHAR2"


def _indent(lines: list[str], level: int = 1) -> list[str]:
    pad = "    " * level
    return [pad + ln for ln in lines]


def _list_local_append(stmt: ast.stmt, ctx: _FnCtx) -> tuple[str, ast.expr] | None:
    """`<list local>.append(<value>)` -> (local name, value)."""
    if (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and stmt.value.func.attr == "append"
        and isinstance(stmt.value.func.value, ast.Name)
        and ctx.locals.get(stmt.value.func.value.id) == "ARRAY"
    ):
        if len(stmt.value.args) != 1:
            raise CodeGenError("`.append(...)` takes exactly one argument")
        return stmt.value.func.value.id, stmt.value.args[0]
    return None


class _AggregateHoister(ast.NodeTransformer):
    """An aggregate inside a larger expression (`round(sum(...), 2)`, `count(...) + 1`) is a loop,
    not an expression: it is computed first into a local of its own, which takes its place."""

    def __init__(
        self,
        translator: _ExprTranslator,
        ctx: _FnCtx,
        loop_counter: itertools.count,
        lines: list[str],
    ):
        self.translator = translator
        self.ctx = ctx
        self.loop_counter = loop_counter
        self.lines = lines

    def visit_Call(self, node: ast.Call) -> ast.expr:
        if not _is_aggregate_call(node, self.translator.function_linker):
            return self.generic_visit(node)  # type: ignore[return-value]
        idx = next(self.loop_counter)
        name = f"agg{idx}"
        var = self.ctx.local_var(name)
        kind = "BOOLEAN" if node.func.id in ("any", "all") else "NUMBER"  # type: ignore[attr-defined]
        self.ctx.locals[name] = kind
        self.ctx.declare(f"{var} {kind};")
        self.lines.extend(
            _materialize_aggregate(node, self.translator, var, "NUMBER", idx, self.ctx.declarations)
        )
        return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)


def _nested_hoister(translator: _ExprTranslator, lines: list[str]) -> _AggregateHoister:
    """The hoister for an aggregate inside an aggregate: what it computes goes into `lines`, which
    the outer loop runs for each element."""
    ctx = translator.ctx
    if not isinstance(ctx, _FnCtx):
        raise CodeGenError(
            "an aggregate inside an aggregate is only written in a rule's expression"
        )
    return _AggregateHoister(translator, ctx, ctx.loop_counter, lines)


def _hoisted(
    value: ast.expr,
    translator: _ExprTranslator,
    ctx: _FnCtx,
    loop_counter: itertools.count,
    lines: list[str],
) -> ast.expr:
    """`value` with its aggregates computed into locals (their loops appended to `lines`)."""
    return _AggregateHoister(translator, ctx, loop_counter, lines).visit(value)


def _translate_fn_body(
    stmts: list[ast.stmt],
    ctx: _FnCtx,
    return_expected: str,
    translator: _ExprTranslator,
    loop_counter: itertools.count,
) -> list[str]:
    out: list[str] = []
    ctx.loop_counter = (
        loop_counter  # the loops (and aggregates) of this function are numbered by it
    )
    for stmt in stmts:
        appended = _list_local_append(stmt, ctx)
        if appended is not None:
            name, value = appended
            var = ctx.local_var(name)
            out.extend(
                _emit_value(
                    value, ctx, translator, loop_counter, lambda e, v=var: f"{v}.append({e});", None
                )
            )
        elif _is_next_index(stmt):
            assert isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call)
            name = _name_of(stmt.targets[0])
            k = _const_int(stmt.value.args[1])
            out.append(f"{ctx.local_var(name)} := {ctx.local_var(f'cnt{k}')};")
            out.append(f"{ctx.local_var(f'cnt{k}')} := {ctx.local_var(f'cnt{k}')} + 1;")
        elif isinstance(stmt, ast.Assign):
            target = stmt.targets[0]
            if not isinstance(target, ast.Name):
                raise CodeGenError("unsupported local assignment target")
            mangled = ctx.local_var(target.id)
            value = stmt.value
            if isinstance(value, ast.List) and not value.elts:
                # a fresh list; (re)initialised where it is assigned, so a list
                # built inside a loop body starts empty on every iteration
                if target.id not in ctx.locals:
                    ctx.locals[target.id] = "ARRAY"
                    ctx.declare(f"{mangled} JSON_ARRAY_T;")
                out.append(f"{mangled} := JSON_ARRAY_T();")
            elif (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in translator.rule_signatures
            ):
                if translator.fn_name is None:
                    raise CodeGenError("rule-function calls need a function-name resolver")
                sig = translator.rule_signatures[value.func.id]
                if len(value.args) != len(sig.param_names):
                    raise CodeGenError(
                        f"'{value.func.id}' takes {len(sig.param_names)} argument(s), "
                        f"got {len(value.args)}"
                    )
                om = f"{mangled}__o"
                if target.id not in ctx.locals:
                    ctx.locals[target.id] = sig.return_expected
                    ctx.declare(f"{mangled} {_decl_type(sig.return_expected)};")
                    ctx.declare(f"{om} BOOLEAN;")
                ctx.omit_flags[target.id] = om
                args = [
                    translator.translate(a, sig.param_expected[i]) for i, a in enumerate(value.args)
                ]
                call = f"{translator.fn_name(value.func.id)}({_call_args(sig, args, _ERRORS_PARAM, om)})"
                out.extend(_isolated_call(value.func.id, call, mangled, om))
            else:
                value = _hoisted(value, translator, ctx, loop_counter, out)
                inferred = infer_type(value, ctx)
                rhs = translator.translate(value, inferred)
                if target.id not in ctx.locals:
                    ctx.locals[target.id] = inferred
                    ctx.declare(f"{mangled} {_decl_type(inferred)};")
                out.append(f"{mangled} := {rhs};")
        elif isinstance(stmt, ast.Return):
            if stmt.value is None:
                out.append("p_omitted := TRUE;")
                out.append("RETURN NULL;")
            elif isinstance(stmt.value, ast.Name) and stmt.value.id == "Null":
                out.append("RETURN NULL;")
            elif _is_dataclass_construction(stmt.value, translator.dataclasses):
                assert isinstance(stmt.value, ast.Call)
                tmp_var = f"v_{ctx.local_prefix}__dc"
                if tmp_var not in ctx.locals:
                    ctx.locals[tmp_var] = "OBJECT"
                    ctx.declarations.append(f"{tmp_var} JSON_OBJECT_T;")
                out.extend(
                    _materialize_dataclass(stmt.value, translator, tmp_var, ctx, loop_counter)
                )
                out.append(f"RETURN {tmp_var};")
            elif _is_aggregate_call(stmt.value, translator.function_linker):
                assert isinstance(stmt.value, ast.Call)
                tmp_var = f"v_{ctx.local_prefix}__agg"
                decl_type = _EXPECTED_TO_DECL_TYPE.get(return_expected, return_expected)
                if tmp_var not in ctx.locals:
                    ctx.locals[tmp_var] = return_expected
                    ctx.declarations.append(f"{tmp_var} {decl_type};")
                out.extend(
                    _materialize_aggregate(
                        stmt.value,
                        translator,
                        tmp_var,
                        return_expected,
                        next(loop_counter),
                        ctx.declarations,
                    )
                )
                out.append(f"IF {tmp_var} IS NULL THEN p_omitted := TRUE; END IF;")
                out.append(f"RETURN {tmp_var};")
            else:
                returned = _hoisted(stmt.value, translator, ctx, loop_counter, out)
                value_sql = translator.translate(returned, return_expected)
                if return_expected in _SCALAR_KINDS and not (
                    isinstance(returned, ast.Constant) and returned.value is not None
                ):
                    # a value that is NULL is nothing to write (`Null`, above, is the explicit null)
                    ret = ctx.local_var("_ret")
                    if ret not in ctx.declared_names:
                        ctx.declared_names.add(ret)
                        ctx.declare(f"{ret} {_decl_type(return_expected)};")
                    out.append(f"{ret} := {value_sql};")
                    out.append(f"IF {ret} IS NULL THEN p_omitted := TRUE; END IF;")
                    out.append(f"RETURN {ret};")
                else:
                    out.append(f"RETURN {value_sql};")
        elif isinstance(stmt, ast.If):
            out.extend(_translate_fn_if(stmt, ctx, return_expected, translator, loop_counter))
        elif isinstance(stmt, ast.For):
            out.extend(_translate_fn_for(stmt, ctx, return_expected, translator, loop_counter))
        elif isinstance(stmt, ast.Continue):
            out.append("CONTINUE;")
        else:
            raise CodeGenError(f"unsupported statement in field-rule body: {type(stmt).__name__}")
    return out


def _translate_fn_for(
    stmt: ast.For,
    ctx: _FnCtx,
    return_expected: str,
    translator: _ExprTranslator,
    loop_counter: itertools.count,
) -> list[str]:
    """A `for` inside a rule function: builds nested output arrays. Supports the
    same iterable forms as a flow-level loop (`enumerate`, `sorted`, a
    filtering comprehension). A leading `if not c: continue` (and the filter a
    comprehension lowers to) becomes `IF c THEN <rest> END IF`, so a NULL
    condition skips the element instead of falling through."""
    try:
        lowered = lower_filtered_iter(stmt, ctx.counter)
        spec = parse_for_iter(lowered.iter)
        item_var, index_var = parse_for_target(lowered.target)
    except (LoopIterError, Exception) as exc:
        if isinstance(exc, CodeGenError):
            raise
        raise CodeGenError(str(exc)) from exc

    n = next(loop_counter)
    arr, k = f"v_forarr_{n}", f"v_i_{n}"
    ctx.declare(f"{arr} JSON_ARRAY_T;")
    lines: list[str] = []
    source = translator.translate(spec.array_expr, "ARRAY")
    lines.append(f"{arr} := {source};")
    for name in (item_var, *([index_var] if index_var else [])):
        if name not in ctx.locals:
            ctx.locals[name] = "OBJECT" if name == item_var else "NUMBER"
            ctx.declare(
                f"{ctx.local_var(name)} {'JSON_OBJECT_T' if name == item_var else 'NUMBER'};"
            )
    if spec.sorts:  # (a list missing from the document is NULL: no elements)
        lines.append(f"IF {arr} IS NOT NULL THEN")
        lines.extend(
            _indent(_sort_passes(arr, n, spec.sorts, ctx.local_var(item_var), translator.translate))
        )
        lines.append("END IF;")
    for name, start, cid in _counted_indexes(lowered.body):
        cnt = ctx.local_var(f"cnt{cid}")
        ctx.declare(f"{cnt} NUMBER;")
        if name not in ctx.locals:
            ctx.locals[name] = "NUMBER"
            ctx.declare(f"{ctx.local_var(name)} NUMBER;")
        lines.append(f"{cnt} := {start};")

    body = lowered.body
    body_filter, rest = extract_continue_filter(body)
    if body_filter is not None:
        body = wrap_filter(body_filter, rest)

    inner = [f"{ctx.local_var(item_var)} := TREAT({arr}.get({k}) AS JSON_OBJECT_T);"]
    if index_var:
        offset = spec.enumerate_start or 0
        inner.append(f"{ctx.local_var(index_var)} := {k}" + (f" + {offset};" if offset else ";"))
    inner.extend(_translate_fn_body(body, ctx, return_expected, translator, loop_counter))
    lines.append(f"IF {arr} IS NOT NULL THEN")
    lines.append(f"    FOR {k} IN 0 .. {arr}.get_size - 1 LOOP")
    lines.extend(_indent(inner, 2))
    lines.append("    END LOOP;")
    lines.append("END IF;")
    return lines


def _translate_fn_if(
    stmt: ast.If,
    ctx: _FnCtx,
    return_expected: str,
    translator: _ExprTranslator,
    loop_counter: itertools.count,
) -> list[str]:
    # an aggregate in a condition is a loop: computed first, where the condition is tested
    lines: list[str] = []
    tests: list[ast.expr] = []
    node: ast.If | None = stmt
    while node is not None:
        tests.append(_hoisted(copy.deepcopy(node.test), translator, ctx, loop_counter, lines))
        orelse = node.orelse
        node = orelse[0] if len(orelse) == 1 and isinstance(orelse[0], ast.If) else None
    lines.append(f"IF {translator.condition(tests[0])} THEN")
    lines.extend(
        _indent(_translate_fn_body(stmt.body, ctx, return_expected, translator, loop_counter))
    )
    orelse = stmt.orelse
    n = 1
    while len(orelse) == 1 and isinstance(orelse[0], ast.If):
        elif_stmt = orelse[0]
        lines.append(f"ELSIF {translator.condition(tests[n])} THEN")
        n += 1
        lines.extend(
            _indent(
                _translate_fn_body(elif_stmt.body, ctx, return_expected, translator, loop_counter)
            )
        )
        orelse = elif_stmt.orelse
    if orelse:
        lines.append("ELSE")
        lines.extend(
            _indent(_translate_fn_body(orelse, ctx, return_expected, translator, loop_counter))
        )
    lines.append("END IF;")
    return lines


@dataclass
class _ListAccumulator:
    field_name: str
    var_name: str
    guarded: bool = False  # written only under a guard: it exists only once `open_var` is TRUE

    @property
    def open_var(self) -> str:
        """TRUE once the array has been created (`out.<array>` reached): it is written only then."""
        return f"v_open_{self.field_name}"


class PlsqlCodeGenerator:
    def __init__(
        self,
        function_linker: FunctionLinker,
        error_code: int = -20000,
        naming: PlsqlNaming | None = None,
    ):
        self.function_linker = function_linker
        self.error_code = error_code
        self.naming = naming or PlsqlNaming()

    # -- module compilation -----------------------------------------------

    def _library_name(self, name: str) -> str | None:
        """Call name of a built-in kept in the functions package (recording the use)."""
        if name not in LIBRARY_FUNCTIONS:
            return None
        self._library_used.add(name)
        return self.naming.library_call(name)

    def _fn_name(self, rule_id: str) -> str:
        """How a rule function is called: by name, it lives in the same package."""
        return _check_identifier(self.naming.rule(self._mapping_id, rule_id))

    def compile_module(
        self,
        tree: ast.Module,
        mapping_id: str,
        scope_resolution=None,
        validation: Validation | None = None,
    ) -> PlsqlUnit:
        self._mapping_id = mapping_id
        self._library_used: set[str] = set()
        self._loop_counter = itertools.count()
        dataclasses = _collect_dataclasses(tree)
        rule_defs: dict[str, ast.FunctionDef] = {}
        flow_stmts: list[ast.stmt] = []

        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom):
                continue
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                continue  # __id__ directive, already handled by the caller
            if isinstance(stmt, ast.ClassDef):
                continue  # already collected into `dataclasses`
            if isinstance(stmt, ast.FunctionDef):
                rule_defs[stmt.name] = stmt
                continue
            flow_stmts.append(stmt)

        rule_signatures = {name: _resolve_signature(fn_def) for name, fn_def in rule_defs.items()}
        for name, fn_def in rule_defs.items():
            rule_signatures[name].records_errors = _calls_rule_function(fn_def, set(rule_defs))

        function_texts = [
            self._compile_rule_function(name, fn_def, rule_signatures, dataclasses)
            for name, fn_def in rule_defs.items()
        ]

        list_accumulators: dict[str, _ListAccumulator] = {}
        body_lines = self._emit_flow(
            flow_stmts,
            loop_vars=[],
            rule_signatures=rule_signatures,
            dataclasses=dataclasses,
            list_accumulators=list_accumulators,
        )

        if validation is not None:
            function_texts += self._schema_functions(validation)
        entry_points = self._render(
            mapping_id,
            body_lines,
            list_accumulators,
            uses_rule_errors=any(sig.records_errors for sig in rule_signatures.values()),
            validation=validation,
        )
        parallel = {
            name: degree
            for name, fn_def in rule_defs.items()
            if (degree := _parallel_degree(fn_def)) is not None
        }
        if parallel:
            entry_points.append(self._parallel_wrapper(mapping_id, parallel))

        return PlsqlUnit(
            mapping_id=mapping_id,
            rule_functions=function_texts,
            entry_points=entry_points,
            library_functions=sorted(self._library_used),
            validated=validation is not None,
        )

    def _schema_name(self, side: str) -> str:
        return _check_identifier(self.naming.rule(self._mapping_id, f"validation_schema_{side}"))

    def _schema_functions(self, validation: Validation) -> list[PlsqlSubprogram]:
        """For each side that validates against its JSON Schema, a private function that gives the
        schema as a CLOB. The text is embedded in the package (written in pieces, a literal is
        short); its hash is in the comment, so a deployed package can be compared with the file."""
        found: list[PlsqlSubprogram] = []
        for side in ("input", "output"):
            text = validation.schemas.get(side) if validation.side(side).schema else None
            if text is None:
                continue
            name = self._schema_name(side)
            pieces = [text[i : i + 1500] for i in range(0, len(text), 1500)] or [""]
            joined = "\n        || ".join(f"TO_CLOB({_quote(piece)})" for piece in pieces)
            spec = f"FUNCTION {name} RETURN CLOB;"
            body = (
                f"-- the {side} JSON Schema, sha256:{schema_hash(text)}\n"
                f"FUNCTION {name} RETURN CLOB IS\nBEGIN\n    RETURN {joined};\nEND {name};"
            )
            found.append(PlsqlSubprogram(name, spec, body))
        return found

    def _parallel_wrapper(self, mapping_id: str, degrees: dict[str, int]) -> PlsqlSubprogram:
        """`map_<id>_fn`: the SQL-callable, `PARALLEL_ENABLE` face of `map_<id>`.

        `PARALLEL_ENABLE` only means something for a function called from a SQL
        statement (Oracle may then run it in parallel-query slaves, one document
        per call); it cannot parallelize a PL/SQL loop. The procedures cannot be
        called from SQL (OUT parameters), hence this scalar wrapper, generated
        only for mappings whose rule functions declare `@parallel`. It calls the
        raising twin: a failing document fails the statement with the usual
        error payload (use `map_<id>_safe` from PL/SQL to collect errors).
        """
        name = _check_identifier(self.naming.entry(mapping_id, "_fn"))
        raising = _check_identifier(self.naming.entry(mapping_id))
        sig = f"FUNCTION {name} (p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE"
        declared = ", ".join(f"{fn} (degree={d})" for fn, d in degrees.items())
        body = (
            f"-- @parallel declared by: {declared}.\n"
            f"-- The degree is chosen by the caller, e.g.\n"
            f"--   SELECT /*+ PARALLEL({max(degrees.values())}) */ {name}(doc) FROM staging\n"
            f"{sig} AS\n"
            "    v_out CLOB;\n"
            "BEGIN\n"
            f"    {raising}(p_src, v_out);\n"
            "    RETURN v_out;\n"
            f"END {name};"
        )
        return PlsqlSubprogram(name, f"{sig};", body)

    def _compile_rule_function(
        self,
        name: str,
        fn_def: ast.FunctionDef,
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
    ) -> PlsqlSubprogram:
        sig = rule_signatures[name]
        ctx = _FnCtx(params=sig.param_names, local_prefix=name)
        translator = _ExprTranslator(
            ctx,
            rule_signatures,
            dataclasses,
            self.function_linker,
            self._fn_name,
            self._library_name,
        )
        body_lines = ["p_omitted := FALSE;"]
        body_lines.extend(
            _translate_fn_body(
                fn_def.body, ctx, sig.return_expected, translator, self._loop_counter
            )
        )

        params = [
            f"p_{pname} IN {ptype}"
            for pname, ptype in zip(sig.param_names, sig.param_plsql_types, strict=True)
        ]
        if sig.records_errors:
            params.append(f"{_ERRORS_PARAM} IN OUT NOCOPY JSON_OBJECT_T")
        params.append("p_omitted OUT BOOLEAN")
        decls = "\n    ".join(ctx.declarations)

        fn_name = _check_identifier(self.naming.rule(self._mapping_id, name))
        signature = f"FUNCTION {fn_name}(" + ", ".join(params) + f") RETURN {sig.return_plsql_type}"
        header = f"{signature} IS\n"
        if decls:
            header += f"    {decls}\n"
        return PlsqlSubprogram(
            name=fn_name,
            spec=f"{signature};",
            body=header + "BEGIN\n" + "\n".join(_indent(body_lines)) + f"\nEND {fn_name};",
        )

    def _emit_flow(
        self,
        stmts: list[ast.stmt],
        loop_vars: list[str],
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
        list_accumulators: dict[str, _ListAccumulator],
    ) -> list[str]:
        ctx = _FlowCtx(loop_vars)
        translator = _ExprTranslator(
            ctx,
            rule_signatures,
            dataclasses,
            self.function_linker,
            self._fn_name,
            self._library_name,
        )
        lines: list[str] = []

        for stmt in stmts:
            if _is_next_index(stmt):
                assert isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call)
                name = _name_of(stmt.targets[0])
                k = _const_int(stmt.value.args[1])
                lines.append(f"v_{name} := v_cnt_{k};")
                lines.append(f"v_cnt_{k} := v_cnt_{k} + 1;")
            elif isinstance(stmt, ast.Assign):
                target = stmt.targets[0]
                if not (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "out"
                ):
                    raise CodeGenError("only `out.<field> = ...` assignments are supported")
                field_name = target.attr
                lines.extend(
                    self._emit_out_write(
                        field_name,
                        stmt.value,
                        ctx,
                        translator,
                        rule_signatures,
                        sink=lambda expr, f=field_name: f"v_out_obj.put({_quote(f)}, {expr});",
                    )
                )
            elif (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and self._is_out_append(stmt.value)
            ):
                call = stmt.value
                assert isinstance(call.func, ast.Attribute)
                out_attr = call.func.value
                assert isinstance(out_attr, ast.Attribute)
                field_name = out_attr.attr
                if field_name not in list_accumulators:
                    list_accumulators[field_name] = _ListAccumulator(
                        field_name, f"v_arr_{field_name}"
                    )
                if len(call.args) != 1:
                    raise CodeGenError("`.append(...)` takes exactly one argument")
                var_name = list_accumulators[field_name].var_name
                lines.extend(
                    self._emit_out_write(
                        field_name,
                        call.args[0],
                        ctx,
                        translator,
                        rule_signatures,
                        sink=lambda expr, v=var_name: f"{v}.append({expr});",
                    )
                )
            elif (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Attribute)
                and isinstance(stmt.value.value, ast.Name)
                and stmt.value.value.id == "out"
            ):  # `out.<array>`: the array exists from here on (even if nothing is appended)
                name = stmt.value.attr
                if name not in list_accumulators:
                    list_accumulators[name] = _ListAccumulator(name, f"v_arr_{name}")
                if getattr(stmt, "guarded", False):
                    list_accumulators[name].guarded = True
                    lines.append(f"{list_accumulators[name].open_var} := TRUE;")
            elif isinstance(stmt, ast.For):
                lines.extend(
                    self._emit_for(stmt, loop_vars, rule_signatures, dataclasses, list_accumulators)
                )
            elif isinstance(stmt, ast.If):
                lines.extend(
                    self._emit_flow_if(
                        stmt, loop_vars, rule_signatures, dataclasses, list_accumulators, translator
                    )
                )
            else:
                raise CodeGenError(f"unsupported statement in mapping body: {type(stmt).__name__}")
        return lines

    def _emit_flow_if(
        self,
        stmt: ast.If,
        loop_vars: list[str],
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
        list_accumulators: dict[str, _ListAccumulator],
        translator: _ExprTranslator,
    ) -> list[str]:
        """Handles a plain `IF`/`ELIF`/`ELSE` at flow level — the shape the
        Loop Fusion Optimizer normalizes bootstrap `if cond: continue`
        filters into (§compiler/loop_fusion.py), and a legitimate direct
        conditional guard around a group of `out.*` writes in its own right."""

        def recurse(body: list[ast.stmt]) -> list[str]:
            return self._emit_flow(body, loop_vars, rule_signatures, dataclasses, list_accumulators)

        lines = [f"IF {translator.condition(stmt.test)} THEN"]
        lines.extend(_indent(recurse(stmt.body)))
        orelse = stmt.orelse
        while len(orelse) == 1 and isinstance(orelse[0], ast.If):
            elif_stmt = orelse[0]
            lines.append(f"ELSIF {translator.condition(elif_stmt.test)} THEN")
            lines.extend(_indent(recurse(elif_stmt.body)))
            orelse = elif_stmt.orelse
        if orelse:
            lines.append("ELSE")
            lines.extend(_indent(recurse(orelse)))
        lines.append("END IF;")
        return lines

    def _emit_out_write(
        self,
        field_name: str,
        value: ast.expr,
        ctx: _FlowCtx,
        translator: _ExprTranslator,
        rule_signatures: dict[str, _RuleSignature],
        sink,
    ) -> list[str]:
        """Emit the guarded statement(s) producing one output value (via
        `sink`, either a `.put()` or an `.append()`), handling both the
        direct-expression shorthand and a call to a rule function (which
        needs the omitted-flag check)."""
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in rule_signatures
        ):
            rule_id = value.func.id
            sig = rule_signatures[rule_id]
            if len(value.args) != len(sig.param_names):
                raise CodeGenError(
                    f"'{rule_id}' takes {len(sig.param_names)} argument(s), got {len(value.args)}"
                )
            arg_exprs = [
                translator.translate(a, sig.param_expected[i]) for i, a in enumerate(value.args)
            ]
            result_var = f"v_result_{rule_id}"
            omitted_var = f"v_omitted_{rule_id}"
            call_expr = (
                f"{self._fn_name(rule_id)}("
                f"{_call_args(sig, arg_exprs, _ERRORS_LOCAL, omitted_var)})"
            )
            return self._guarded(
                rule_id,
                declare=[
                    f"{result_var} {_decl_type(sig.return_expected)};",
                    f"{omitted_var} BOOLEAN;",
                ],
                body=[
                    f"{result_var} := {call_expr};",
                    f"IF NOT {omitted_var} THEN",
                    f"    {sink(result_var)}",
                    "END IF;",
                ],
            )
        if _is_dataclass_construction(value, translator.dataclasses):
            assert isinstance(value, ast.Call)
            tmp_var = f"v_dc_{field_name}"
            declare = [f"{tmp_var} JSON_OBJECT_T;"]
            setup_lines = _materialize_dataclass(value, translator, tmp_var, declarations=declare)
            return self._guarded(field_name, declare=declare, body=[*setup_lines, sink(tmp_var)])
        if _is_aggregate_call(value, translator.function_linker):
            assert isinstance(value, ast.Call)
            fn_ctx_for_infer = _FnCtx(params=[], local_prefix="_")
            inferred = infer_type(value, fn_ctx_for_infer)
            tmp_var = f"v_agg_{field_name}"
            decl_type = _EXPECTED_TO_DECL_TYPE.get(inferred, inferred)
            declare = [f"{tmp_var} {decl_type};"]
            setup_lines = _materialize_aggregate(
                value, translator, tmp_var, inferred, next(self._loop_counter), declare
            )
            body = [
                *setup_lines,
                f"IF {tmp_var} IS NOT NULL THEN",
                f"    {sink(tmp_var)}",
                "END IF;",
            ]
            return self._guarded(field_name, declare=declare, body=body)
        fn_ctx_for_infer = _FnCtx(params=[], local_prefix="_")
        inferred = infer_type(value, fn_ctx_for_infer)
        expr = translator.translate(value, inferred)
        if _is_explicit_null(value):
            return self._guarded(field_name, declare=[], body=[sink(_TYPED_NULL)])
        declare: list[str] = []
        body = _write_unless_null(expr, inferred, sink, declare.append, f"o_{field_name}")
        return self._guarded(field_name, declare=declare, body=body)

    def _guarded(self, rule_id: str, declare: list[str], body: list[str]) -> list[str]:
        lines = ["DECLARE"] if declare else []
        lines.extend(_indent(declare))
        lines.append("BEGIN")
        lines.extend(_indent(body))
        lines.append("EXCEPTION")
        lines.append("    WHEN OTHERS THEN")
        lines.append(f"        IF NOT v_errors.EXISTS({_quote(rule_id)}) THEN")
        lines.append(f"            v_errors({_quote(rule_id)}) := SQLERRM;")
        lines.append("        END IF;")
        lines.append("END;")
        return lines

    def _emit_for(
        self,
        stmt: ast.For,
        loop_vars: list[str],
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
        list_accumulators: dict[str, _ListAccumulator],
    ) -> list[str]:
        try:
            item_var, index_var = parse_for_target(stmt.target)
            iter_spec = parse_for_iter(stmt.iter)
        except LoopIterError as exc:
            raise CodeGenError(str(exc)) from exc

        if iter_spec.filter_expr is not None:
            raise CodeGenError(
                "a filtering comprehension in a `for` iterable must be lowered by the "
                "Loop Fusion Optimizer before code generation"
            )
        outer_ctx = _FlowCtx(loop_vars)
        outer_translator = _ExprTranslator(
            outer_ctx,
            rule_signatures,
            dataclasses,
            self.function_linker,
            self._fn_name,
            self._library_name,
        )
        source_expr = outer_translator.translate(iter_spec.array_expr, "ARRAY")

        idx = next(self._loop_counter)
        arr_var = f"v_forarr_{idx}"
        idx_var = f"v_i_{idx}"

        # The in-place sort must work on a copy: `get_Array` hands back a
        # reference into the source document, so sorting it directly would
        # reorder the input under every other loop reading the same array.
        over_document = (
            isinstance(iter_spec.array_expr, ast.Name) and iter_spec.array_expr.id == "root"
        )
        if over_document:
            # `source: $`: the document is the one element of the loop
            setup_lines = [f"{arr_var} JSON_ARRAY_T := JSON_ARRAY_T();"]
        else:
            setup_lines = [f"{arr_var} JSON_ARRAY_T := {source_expr};"]
        sort_lines: list[str] = []
        if iter_spec.sorts:
            key_translator = _ExprTranslator(
                _FlowCtx([*loop_vars, item_var]),
                rule_signatures,
                dataclasses,
                self.function_linker,
                self._fn_name,
                self._library_name,
            )
            sort_lines = _sort_passes(
                arr_var, idx, iter_spec.sorts, f"v_{item_var}", key_translator.translate, True
            )

        inner_loop_vars = [*loop_vars, item_var]
        counted = _counted_indexes(stmt.body)
        counter_decl = ""
        for name, start, k in counted:
            setup_lines.append(f"v_cnt_{k} NUMBER := {start};")
            if name not in inner_loop_vars:
                inner_loop_vars.append(_IndexVar(name))
                counter_decl += f"\n            v_{name} NUMBER;"
        index_decl = ""
        if index_var is not None:
            inner_loop_vars.append(_IndexVar(index_var))
            offset = iter_spec.enumerate_start or 0
            offset_expr = f"{idx_var}" if offset == 0 else f"{idx_var} + {offset}"
            index_decl = f"\n            v_{index_var} NUMBER := {offset_expr};"
        index_decl += counter_decl

        inner_lines = self._emit_flow(
            stmt.body, inner_loop_vars, rule_signatures, dataclasses, list_accumulators
        )

        lines = [
            "DECLARE",
            *(f"    {ln}" for ln in setup_lines),
            "BEGIN",
        ]
        if over_document:
            lines.append(f"    {arr_var}.append({source_expr});")
        # a list that is missing from the document has no elements (it is NULL here)
        lines.append(f"    IF {arr_var} IS NOT NULL THEN")
        lines.extend(_indent(sort_lines, 2))
        lines.extend(
            [
                f"        FOR {idx_var} IN 0 .. {arr_var}.get_size - 1 LOOP",
                "            DECLARE",
                f"                v_{item_var} JSON_OBJECT_T := TREAT({arr_var}.get({idx_var}) AS JSON_OBJECT_T);"
                f"{index_decl}",
                "            BEGIN",
            ]
        )
        lines.extend(_indent(inner_lines, 4))
        lines.extend(["            END;", "        END LOOP;", "    END IF;", "END;"])
        return lines

    @staticmethod
    def _is_out_append(call: ast.Call) -> bool:
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "append":
            return False
        base = call.func.value
        return (
            isinstance(base, ast.Attribute)
            and isinstance(base.value, ast.Name)
            and base.value.id == "out"
        )

    # -- validation ---------------------------------------------------------

    def _check_lines(
        self, validation: Validation | None, side: str, document_clob: str, root: str
    ) -> list[str]:
        """The PL/SQL that checks one side: the JSON Schema first, then each extra check.
        `document_clob` is the document as text, `root` the JSON object the check functions
        read."""
        if validation is None:
            return []
        lines: list[str] = []
        spec = validation.side(side)
        failed = f"v_schema_failed_{side}"
        if spec.schema and side in validation.schemas:
            code = _quote(SCHEMA_CODE[side])
            schema = self._schema_name(side)
            lines += [
                "DECLARE",
                f"    v_doc    CLOB := {document_clob};",
                f"    v_schema CLOB := {schema};",  # a SQL statement cannot call a private function
                "    v_valid  NUMBER;",
                "    v_paths  VARCHAR2(300);",
                "    v_path   VARCHAR2(200);",
                "    v_rep    VARCHAR2(4000);",
                "    v_errs   JSON_ARRAY_T;",
                "BEGIN",
                "    SELECT DBMS_JSON_SCHEMA.IS_VALID(JSON(v_doc), JSON(v_schema)) "
                "INTO v_valid FROM dual;",
                "    IF v_valid = 0 THEN",
                f"        {failed} := TRUE;",
                "        BEGIN  -- where the document differs (the validator's own texts are not shipped)",
                "            SELECT JSON_QUERY(DBMS_JSON_SCHEMA.VALIDATE_REPORT("
                "JSON(v_doc), JSON(v_schema)), '$.errors' RETURNING VARCHAR2(4000)) INTO v_rep FROM dual;",
                "            v_errs := JSON_ARRAY_T(v_rep);",
                "            FOR v_j IN 0 .. LEAST(v_errs.get_size, 6) - 1 LOOP",
                "                v_path := TREAT(v_errs.get(v_j) AS JSON_OBJECT_T).get_String('instancePath');",
                "                IF v_path <> '$' AND NVL(INSTR(v_paths, v_path), 0) = 0"
                " AND NVL(LENGTH(v_paths), 0) < 200 THEN",
                "                    v_paths := v_paths || CASE WHEN v_paths IS NULL THEN '' ELSE ', ' END || v_path;",
                "                END IF;",
                "            END LOOP;",
                "        EXCEPTION WHEN OTHERS THEN NULL;",
                "        END;",
                f"        add_failed({_quote(side)}, {code}, 'does not match the JSON Schema'"
                " || CASE WHEN v_paths IS NULL THEN '' ELSE ': ' || v_paths END, 'reject');",
                "    END IF;",
                "END;",
            ]
        for check in spec.checks:
            # a check that cannot run on a document the schema refused is not reported: the schema
            # check already says it is not of the shape the check assumes
            lines += [
                "DECLARE",
                "    v_verdict BOOLEAN;",
                "    v_omitted BOOLEAN;",
                "BEGIN",
                f"    v_verdict := {self._fn_name(check.fn)}({root}, v_omitted);",
                "    IF NOT COALESCE(v_verdict, FALSE) THEN",  # only a true verdict passes
                f"        add_failed({_quote(side)}, {_quote(check.code)}, "
                f"{_quote(check.message)}, {_quote(check.action)});",
                "    END IF;",
                "EXCEPTION",
                "    WHEN OTHERS THEN",
                f"        IF NOT {failed} THEN",
                f"            add_failed({_quote(side)}, {_quote(check.code)}, "
                f"{_quote(check.message)} || ' (the check could not be evaluated: ' || SQLERRM || ')', "
                f"{_quote(check.action)});",
                "        END IF;",
                "END;",
            ]
        return lines

    def _reject_lines(self, mapping_id: str) -> list[str]:
        """Raises the reserved error for a rejected document: the payload names the failed checks
        (side, code, action; the messages are in the report of `map_<id>_safe`)."""
        return [
            "DECLARE",
            "    v_checks  JSON_ARRAY_T := JSON_ARRAY_T();",
            "    v_check   JSON_OBJECT_T;",
            "    v_payload JSON_OBJECT_T := JSON_OBJECT_T();",
            "BEGIN",
            "    FOR v_i IN 0 .. v_report.get_size - 1 LOOP",
            "        v_check := JSON_OBJECT_T();",
            *(
                f"        v_check.put({_quote(k)}, "
                f"TREAT(v_report.get(v_i) AS JSON_OBJECT_T).get_string({_quote(k)}));"
                for k in ("side", "code", "action")
            ),
            "        v_checks.append(v_check);",
            "    END LOOP;",
            f"    v_payload.put('mapping', {_quote(mapping_id)});",
            "    v_payload.put('rejected', TRUE);",
            "    v_payload.put('checks', v_checks);",
            f"    RAISE_APPLICATION_ERROR({self.error_code}, v_payload.to_string());",
            "END;",
        ]

    # -- rendering ----------------------------------------------------------

    def _render(
        self,
        mapping_id: str,
        body_lines: list[str],
        list_accumulators: dict[str, _ListAccumulator],
        uses_rule_errors: bool = False,
        validation: Validation | None = None,
    ) -> list[PlsqlSubprogram]:
        accumulator_decl_lines = [
            line
            for acc in list_accumulators.values()
            for line in (
                f"{acc.var_name} JSON_ARRAY_T := JSON_ARRAY_T();",
                *([f"{acc.open_var} BOOLEAN := FALSE;"] if acc.guarded else []),
            )
        ]
        accumulator_put_lines = [
            f"IF {acc.open_var} THEN v_out_obj.put({_quote(acc.field_name)}, {acc.var_name}); END IF;"
            if acc.guarded
            else f"v_out_obj.put({_quote(acc.field_name)}, {acc.var_name});"
            for acc in list_accumulators.values()
        ]

        shared_decls = "\n".join(
            [
                "v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);",
                "v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();",
                "TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);",
                "v_errors   t_error_map;",
                *(
                    [f"{_ERRORS_LOCAL} JSON_OBJECT_T := JSON_OBJECT_T();"]
                    if uses_rule_errors
                    else []
                ),
                *accumulator_decl_lines,
                *(_REPORT_DECLS if validation is not None else []),
            ]
        )

        body = "\n".join(body_lines)
        input_checks = self._check_lines(validation, "input", "p_src", "v_srcroot")
        output_checks = self._check_lines(validation, "output", "v_out_obj.TO_CLOB()", "v_out_obj")

        # Byte-budget-aware truncation (§Runtime error semantics: "20 entries,
        # or the byte budget ... whichever is hit first"). The M0.5 Oracle
        # spike found that neither `SQLERRM` (hard-capped at 512 bytes by
        # Oracle) nor `DBMS_UTILITY.FORMAT_ERROR_STACK` (observed ~1899 bytes
        # for a message > ~1970 bytes) truncate *cleanly* at a JSON boundary —
        # they just cut the character stream, corrupting the JSON. So this
        # generated code enforces the budget itself, before raising, by
        # measuring the candidate payload with LENGTHB and stopping before
        # the next entry would push it past `_ERROR_PAYLOAD_BYTE_BUDGET`.
        # Callers must read the message via `DBMS_UTILITY.FORMAT_ERROR_STACK`,
        # not bare `SQLERRM`, or they will still see it cut off at 512 bytes.
        # Failures of nested members were recorded by the rule functions (not raised):
        # fold them into `v_errors` so both entry points report them like any other.
        merge_rule_errors_lines = (
            [
                "DECLARE",
                f"    v_rule_keys JSON_KEY_LIST := {_ERRORS_LOCAL}.get_keys;",
                "BEGIN",
                "    FOR v_k IN 1 .. v_rule_keys.COUNT LOOP",
                "        IF NOT v_errors.EXISTS(v_rule_keys(v_k)) THEN",
                f"            v_errors(v_rule_keys(v_k)) := {_ERRORS_LOCAL}.get_String(v_rule_keys(v_k));",
                "        END IF;",
                "    END LOOP;",
                "END;",
            ]
            if uses_rule_errors
            else []
        )

        raising_tail_lines = [
            *merge_rule_errors_lines,
            "IF v_errors.COUNT > 0 THEN",
            "    DECLARE",
            "        v_err_arr   JSON_ARRAY_T := JSON_ARRAY_T();",
            "        v_err_obj   JSON_OBJECT_T;",
            "        v_key       VARCHAR2(200);",
            "        v_shown     PLS_INTEGER := 0;",
            "        v_payload   JSON_OBJECT_T := JSON_OBJECT_T();",
            "        v_base_len  PLS_INTEGER;",
            "        v_running_len PLS_INTEGER;",
            "    BEGIN",
            f"        v_payload.put('mapping', {_quote(mapping_id)});",
            "        v_payload.put('total_errors', v_errors.COUNT);",
            "        v_payload.put('shown', 0);",
            "        v_payload.put('errors', v_err_arr);",
            "        v_base_len := LENGTHB(v_payload.to_string());",
            "        v_running_len := v_base_len;",
            "        v_key := v_errors.FIRST;",
            "        WHILE v_key IS NOT NULL AND v_shown < 20 LOOP",
            "            v_err_obj := JSON_OBJECT_T();",
            "            v_err_obj.put('rule', v_key);",
            "            v_err_obj.put('cause', v_errors(v_key));",
            "            EXIT WHEN v_running_len + LENGTHB(v_err_obj.to_string()) + 1"
            f" > {_ERROR_PAYLOAD_BYTE_BUDGET};",
            "            v_err_arr.append(v_err_obj);",
            "            v_running_len := v_running_len + LENGTHB(v_err_obj.to_string()) + 1;",
            "            v_shown := v_shown + 1;",
            "            v_key := v_errors.NEXT(v_key);",
            "        END LOOP;",
            "        v_payload := JSON_OBJECT_T();",
            f"        v_payload.put('mapping', {_quote(mapping_id)});",
            "        v_payload.put('total_errors', v_errors.COUNT);",
            "        v_payload.put('shown', v_shown);",
            "        v_payload.put('errors', v_err_arr);",
            f"        RAISE_APPLICATION_ERROR({self.error_code}, v_payload.to_string());",
            "    END;",
            "END IF;",
            *accumulator_put_lines,
            "p_out := v_out_obj.TO_CLOB();",
        ]

        safe_tail_lines = [
            *merge_rule_errors_lines,
            "DECLARE",
            "    v_err_arr JSON_ARRAY_T := JSON_ARRAY_T();",
            "    v_err_obj JSON_OBJECT_T;",
            "    v_key     VARCHAR2(200);",
            "BEGIN",
            "    v_key := v_errors.FIRST;",
            "    WHILE v_key IS NOT NULL LOOP",
            "        v_err_obj := JSON_OBJECT_T();",
            "        v_err_obj.put('rule', v_key);",
            "        v_err_obj.put('cause', v_errors(v_key));",
            "        v_err_arr.append(v_err_obj);",
            "        v_key := v_errors.NEXT(v_key);",
            "    END LOOP;",
            "    p_err := v_err_arr.to_clob();",
            "END;",
            *accumulator_put_lines,
            "p_out := v_out_obj.TO_CLOB();",
        ]

        raising_name = _check_identifier(self.naming.entry(mapping_id))
        safe_name = _check_identifier(self.naming.entry(mapping_id, "_safe"))
        raising_sig = f"PROCEDURE {raising_name} (\n    p_src IN  CLOB,\n    p_out OUT CLOB\n)"
        safe_sig = (
            f"PROCEDURE {safe_name} (\n"
            "    p_src IN  CLOB,\n    p_out OUT CLOB,\n    p_err OUT CLOB\n)"
        )

        if validation is None:
            raising_text = f"{body}\n\n{chr(10).join(raising_tail_lines)}"
            safe_text = f"{body}\n\n{chr(10).join(safe_tail_lines)}"
            safe_sig_final = safe_sig
        else:
            reject_lines = self._reject_lines(mapping_id)
            # a rejected input runs no rule; the output is checked once it is complete
            raising_text = "\n".join(
                [
                    *input_checks,
                    "IF v_rejected THEN",
                    *_indent(reject_lines),
                    "END IF;",
                    body,
                    "",
                    *raising_tail_lines[:-1],
                    *output_checks,
                    "IF v_rejected THEN",
                    *_indent(reject_lines),
                    "END IF;",
                    raising_tail_lines[-1],
                ]
            )
            safe_text = "\n".join(
                [
                    "p_err := '[]';",
                    *input_checks,
                    "IF NOT v_rejected THEN",
                    *_indent(body.split("\n")),
                    "",
                    *_indent(safe_tail_lines[:-1]),
                    *_indent(output_checks),
                    "END IF;",
                    "p_report := v_report.to_clob();",
                    "IF v_rejected THEN p_out := NULL; ELSE p_out := v_out_obj.TO_CLOB(); END IF;",
                ]
            )
            safe_sig_final = safe_sig.replace(
                "p_err OUT CLOB\n)", "p_err OUT CLOB,\n    p_report OUT CLOB\n)"
            )

        raising_proc = (
            f"{raising_sig} AS\n"
            f"{_indent_block(shared_decls)}\n"
            "BEGIN\n"
            f"{_indent_block(raising_text)}\n"
            f"END {raising_name};"
        )

        safe_proc = (
            f"{safe_sig_final} AS\n"
            f"{_indent_block(shared_decls)}\n"
            "BEGIN\n"
            f"{_indent_block(safe_text)}\n"
            f"END {safe_name};"
        )

        return [
            PlsqlSubprogram(raising_name, f"{raising_sig};", raising_proc),
            PlsqlSubprogram(safe_name, f"{safe_sig_final};", safe_proc),
        ]


def _sort_passes(
    arr: str,
    idx: int,
    sorts: tuple[SortSpec, ...],
    item_local: str,
    translate: Callable[[ast.expr, str | None], str],
    declare_item: bool = False,
) -> list[str]:
    """The ordering of the array `arr` by each of `sorts`, in the order they are applied: one stable
    pass per key (the last key decides first), each into a new array, so that the document's own
    array is never reordered under the other loops that read it."""
    lines: list[str] = []
    for n, spec in enumerate(sorts):
        key_code = None
        if spec.by is not None:
            key_code = translate(spec.by, "NUMBER" if spec.kind == "number" else "VARCHAR2")
        lines.extend(_sort_pass(arr, f"{idx}_{n}", spec, item_local, key_code, declare_item))
    return lines


def _sort_pass(
    arr: str, tag: str, spec: SortSpec, item_local: str, key_code: str | None, declare_item: bool
) -> list[str]:
    """One pass: the keys are computed once per element, then the positions are put in order by a
    stable insertion sort (an element with no key goes first or last as asked, whichever the
    direction) and the elements are copied in that order. A field key compares as JSON values
    (`compare_to`: numbers and texts alike); an expression key as a NUMBER or a text, as its
    `kind` says."""
    key, order, out = f"v_sortkey_{tag}", f"v_sortord_{tag}", f"v_sorted_{tag}"
    tmp, j = f"v_sorttmp_{tag}", f"v_sortj_{tag}"
    i, k = f"v_sorti_{tag}", f"v_sortk_{tag}"
    cmp_, nul = f"v_sortcmp_{tag}", f"v_sortnul_{tag}"
    if spec.field is not None:
        key_type = "JSON_ELEMENT_T"
        fetch = [f"{key}({i}) := TREAT({arr}.get({i}) AS JSON_OBJECT_T).get({_quote(spec.field)});"]
        is_null = f"{key}(p) IS NULL OR {key}(p).is_Null"
        less, more = f"{key}(a).compare_to({key}(b)) < 0", f"{key}(a).compare_to({key}(b)) > 0"
    else:
        key_type = "NUMBER" if spec.kind == "number" else "VARCHAR2(4000 CHAR)"
        fetch = [
            f"{item_local} := TREAT({arr}.get({i}) AS JSON_OBJECT_T);",
            f"{key}({i}) := {key_code};",
        ]
        is_null = f"{key}(p) IS NULL"
        less, more = f"{key}(a) < {key}(b)", f"{key}(a) > {key}(b)"
    first = -1 if spec.nulls_first else 1  # where an element with no key goes against one with
    before, after = (1, -1) if spec.reverse else (-1, 1)
    return [
        "DECLARE",
        f"    TYPE t_key_{tag} IS TABLE OF {key_type} INDEX BY PLS_INTEGER;",
        f"    TYPE t_ord_{tag} IS TABLE OF PLS_INTEGER INDEX BY PLS_INTEGER;",
        f"    {key} t_key_{tag};",
        f"    {order} t_ord_{tag};",
        f"    {out} JSON_ARRAY_T := JSON_ARRAY_T();",
        f"    {tmp} PLS_INTEGER;",
        f"    {j} PLS_INTEGER;",
        *([f"    {item_local} JSON_OBJECT_T;"] if declare_item and spec.by is not None else []),
        f"    FUNCTION {nul}(p IN PLS_INTEGER) RETURN BOOLEAN IS",
        f"    BEGIN RETURN {is_null}; END;",
        f"    FUNCTION {cmp_}(a IN PLS_INTEGER, b IN PLS_INTEGER) RETURN PLS_INTEGER IS",
        "    BEGIN",
        f"        IF {nul}(a) THEN RETURN CASE WHEN {nul}(b) THEN 0 ELSE {first} END; END IF;",
        f"        IF {nul}(b) THEN RETURN {-first}; END IF;",
        f"        IF {less} THEN RETURN {before}; END IF;",
        f"        IF {more} THEN RETURN {after}; END IF;",
        "        RETURN 0;",
        "    END;",
        "BEGIN",
        f"    FOR {i} IN 0 .. {arr}.get_size - 1 LOOP",
        *(f"        {line}" for line in fetch),
        f"        {order}({i}) := {i};",
        "    END LOOP;",
        f"    FOR {k} IN 1 .. {arr}.get_size - 1 LOOP",
        f"        {tmp} := {order}({k});",
        f"        {j} := {k} - 1;",
        f"        WHILE {j} >= 0 AND {cmp_}({order}({j}), {tmp}) > 0 LOOP",
        f"            {order}({j} + 1) := {order}({j});",
        f"            {j} := {j} - 1;",
        "        END LOOP;",
        f"        {order}({j} + 1) := {tmp};",
        "    END LOOP;",
        f"    FOR {i} IN 0 .. {arr}.get_size - 1 LOOP",
        f"        {out}.append({arr}.get({order}({i})));",
        "    END LOOP;",
        f"    {arr} := {out};",
        "END;",
    ]


def _decl_type(expected_kind: str) -> str:
    return _EXPECTED_TO_DECL_TYPE.get(expected_kind, "JSON_OBJECT_T")


def _indent_block(text: str, level: int = 1) -> str:
    pad = "    " * level
    return "\n".join(pad + ln if ln else ln for ln in text.split("\n"))
