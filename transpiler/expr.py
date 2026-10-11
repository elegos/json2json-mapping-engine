"""Expression blocks (used by the `build` stage) (docs/ARCHITECTURE.md, §Expression language).

An expression block is Python: optional local assignments, then a value
(`return` is optional on the last line). After anchor resolution `ast.parse()`
is all the parsing needed. This stage also:

- mangles local variable names with the rule's id prefix (`base` ->
  `ord_lin_base`) so fields sharing one composite function cannot collide;
- rewrites a trailing bare expression into a `return`;
- reports what the block can do (`return Null`, bare `return`), which drive the
  generated function's return annotation.

Blocks are used for `transform.expression`, `transform.code_override` (developer
dialect — same shape, no anchors) and `guard`.
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass

from transpiler.anchors import _split_strings
from transpiler.model import FnYamlError

_RESERVED_PARAMS = {"root", "out", "Null"}
_RESERVED_PATTERN = re.compile(r"^(src|index)\d*$")


COMMENT_MARK = "@@comment@@ "


def comment_stmt(text: str) -> ast.stmt:
    """A marker statement that the final render turns into a `# text` line
    (`ast.unparse` drops real comments)."""
    return ast.Expr(value=ast.Constant(value=COMMENT_MARK + text))


def is_comment(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
        and stmt.value.value.startswith(COMMENT_MARK)
    )


@dataclass
class Block:
    stmts: list[ast.stmt]  # finalized: every path ends in a Return
    returns_null: bool
    can_omit: bool

    @property
    def is_simple(self) -> bool:
        """assign* then one `return <value>` — expressible as a dataclass kwarg."""
        *pre, last = self.stmts
        return (
            all(isinstance(s, ast.Assign) or is_comment(s) for s in pre)
            and isinstance(last, ast.Return)
            and last.value is not None
            and not self.returns_null
        )

    @property
    def pre(self) -> list[ast.stmt]:
        return self.stmts[:-1]

    @property
    def value(self) -> ast.expr:
        last = self.stmts[-1]
        assert isinstance(last, ast.Return) and last.value is not None
        return last.value


class _Rename(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id in self.mapping:
            return ast.copy_location(ast.Name(id=self.mapping[node.id], ctx=node.ctx), node)
        return node


# what a functional coming from another language is likely to type, with what it means here
_FOREIGN = (
    (re.compile(r"&&"), "`&&` is not valid: write `and`"),
    (re.compile(r"\|\|"), "`||` is not valid: write `or`"),
    (re.compile(r"[!=]==|<>"), "use `==` to compare and `!=` for 'different'"),
    (re.compile(r"!(?!=)"), "`!` is not valid: write `not`"),
    (
        re.compile(r"\?"),
        "there is no `cond ? a : b`: write `a if cond else b`, or `if_else(cond, a, b)`",
    ),
    (re.compile(r";"), "`;` is not valid: put one statement per line"),
)
_INTERNAL_NAME = re.compile(r"_(?:L|LK_|I)\w*$")
_TOKEN = re.compile(r"\w+|\S")


def explain_syntax_error(text: str, exc: SyntaxError) -> str:
    """What is wrong with `text`, in a functional's words. `exc` is Python's own error for it
    (whose "invalid syntax" says nothing); where the likely mistake is one made in another
    language, say what to write here instead."""
    # the string literals are blanked, so `"a && b"` is not read as an operator
    masked = "".join(" " * len(c) if lit else c for lit, c in _split_strings(text))
    for pattern, advice in _FOREIGN:
        if pattern.search(masked):
            return advice
    msg = exc.msg
    if msg.startswith("unterminated string literal"):
        return "a text is not closed: the closing quote is missing"
    if msg == "invalid syntax":
        lines = text.splitlines() or [""]
        line = lines[min((exc.lineno or 1), len(lines)) - 1]
        offset = (exc.offset or 0) - 1
        if offset < 0 or not line[offset:].strip():
            return "it ends too soon: a value is missing after the last operator"
        token = _TOKEN.match(line, offset)
        shown = token.group() if token else ""
        if _INTERNAL_NAME.match(shown):
            return "a reference is not where it can be: an operator may be missing before it"
        hint = " (is an operator missing before it?)" if shown[:1].isalnum() else ""
        return f"unexpected `{shown}`{hint}"
    return msg


def _assigned_names(stmts: list[ast.stmt]) -> set[str]:
    names: set[str] = set()
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
    return names


def _check_shape(stmts: list[ast.stmt], where: str) -> None:
    for stmt in stmts:
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise FnYamlError(
                    f"{where}: only `name = <expression>` assignments are allowed "
                    "(to compare two values, write `==`)"
                )
        elif isinstance(stmt, ast.If):
            _check_shape(stmt.body, where)
            _check_shape(stmt.orelse, where)
        elif isinstance(stmt, (ast.Return, ast.Expr)):
            pass
        else:
            raise FnYamlError(
                f"{where}: unsupported statement '{type(stmt).__name__}' in an expression block "
                "(allowed: assignments, if/elif/else, return, a final expression)"
            )


def _finalize(stmts: list[ast.stmt], where: str, top: bool = True) -> list[ast.stmt]:
    """Turn the trailing expression into a return; require every path to end in one."""
    if not stmts:
        raise FnYamlError(f"{where}: empty block")
    *head, last = stmts
    for s in head:
        if isinstance(s, ast.Expr):
            raise FnYamlError(f"{where}: a bare expression is only allowed as the last line")
    if isinstance(last, ast.Expr):
        last = ast.Return(value=last.value)
    elif isinstance(last, ast.If):
        if not last.orelse:
            raise FnYamlError(f"{where}: an 'if' at the end of a block needs an 'else' branch")
        last.body = _finalize(last.body, where, top=False)
        last.orelse = _finalize(last.orelse, where, top=False)
    elif not isinstance(last, ast.Return):
        raise FnYamlError(f"{where}: the block must end with a value or a return")
    return [*head, last]


def parse_block(text: str, prefix: str, where: str) -> Block:
    source = textwrap.dedent(text).strip("\n")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        at = f" (line {exc.lineno})" if "\n" in source else ""
        raise FnYamlError(
            f"{where}: invalid expression: {explain_syntax_error(source, exc)}{at}"
        ) from exc
    _check_shape(tree.body, where)

    names = _assigned_names(tree.body)
    clash = {n for n in names if n in _RESERVED_PARAMS or _RESERVED_PATTERN.match(n)}
    if clash:
        raise FnYamlError(f"{where}: cannot assign reserved name(s): {', '.join(sorted(clash))}")
    renamer = _Rename({n: f"{prefix}_{n}" for n in names})
    body = [renamer.visit(s) for s in tree.body]
    stmts = _finalize(body, where)

    returns_null = can_omit = False
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Return):
                if node.value is None:
                    can_omit = True
                elif isinstance(node.value, ast.Name) and node.value.id == "Null":
                    returns_null = True
    for stmt in stmts:
        ast.fix_missing_locations(stmt)
    return Block(stmts=stmts, returns_null=returns_null, can_omit=can_omit)
