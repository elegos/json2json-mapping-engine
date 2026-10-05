"""The registry of functions callable from a mapping: the built-ins and the project's own.

Both are plain typed Python (`compiler/builtins.py`, the project's `fn/*.fn`) and are read
with `ast`, never imported: a project file is never executed by the tool. A function from the
project replaces a built-in with the same name (docs/ARCHITECTURE.md, §Project functions).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


def special(function):
    """Marker for a built-in typed by hand in the type checker (it only labels the function)."""
    return function


@dataclass(frozen=True)
class Param:
    name: str
    annotation: str  # source text of the annotation; "" when there is none
    default: str | None = None  # source text of the default; None = required
    variadic: bool = False  # `*name`


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    params: tuple[Param, ...]
    returns: str  # source text of the return annotation; "" when there is none
    doc: str = ""
    origin: str = "built-in"  # "built-in" or the project file it comes from
    special: bool = False  # typed by hand (`@special`)
    overrides: dict[str, str] = field(default_factory=dict)  # target -> verbatim template
    source: str = ""  # the function as written, without its decorators
    # runnable as Python: its body is code (not a stub), or it has an `@override(python=...)`;
    # a function only written out for another target is not, and the Python backend cannot run it
    python_code: bool = True

    def signature(self) -> str:
        """`split_first(s, sep)`, as shown while typing."""
        shown = []
        for p in self.params:
            text = ("*" if p.variadic else "") + p.name
            if p.default is not None:
                text += "?"
            shown.append(text)
        return f"{self.name}({', '.join(shown)})"


def _decorators(node: ast.FunctionDef) -> tuple[bool, dict[str, str]]:
    special, overrides = False, {}
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "special":
            special = True
        elif (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "override"
        ):
            for kw in dec.keywords:
                if (
                    kw.arg
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    overrides[kw.arg] = kw.value.value
    return special, overrides


def _is_stub(node: ast.FunctionDef) -> bool:
    """A body that does nothing: only `...`, `pass`, `raise NotImplementedError` (after a docstring)."""
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return True

    def trivial(stmt: ast.stmt) -> bool:
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            return stmt.value.value is ...
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            target = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
            return isinstance(target, ast.Name) and target.id == "NotImplementedError"
        return False

    return all(trivial(stmt) for stmt in body)


def read_functions(source: str, origin: str = "built-in") -> dict[str, FunctionInfo]:
    """The public top-level functions of a source text (names starting with `_` are helpers)."""
    found: dict[str, FunctionInfo] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
            continue
        a = node.args
        plain = [*a.posonlyargs, *a.args]
        defaults: list[ast.expr | None] = [None] * (len(plain) - len(a.defaults)) + list(a.defaults)
        params = [
            Param(
                p.arg,
                ast.unparse(p.annotation) if p.annotation else "",
                ast.unparse(d) if d is not None else None,
            )
            for p, d in zip(plain, defaults, strict=True)
        ]
        if a.vararg:
            ann = ast.unparse(a.vararg.annotation) if a.vararg.annotation else ""
            params.append(Param(a.vararg.arg, ann, None, variadic=True))
        special, overrides = _decorators(node)
        decorators, node.decorator_list = node.decorator_list, []
        source_text = ast.unparse(node)
        node.decorator_list = decorators
        found[node.name] = FunctionInfo(
            name=node.name,
            params=tuple(params),
            returns=ast.unparse(node.returns) if node.returns else "",
            doc=ast.get_docstring(node) or "",
            origin=origin,
            special=special,
            overrides=overrides,
            source=source_text,
            # the built-ins run on every backend (`parse_date` is given its code by the Python runtime)
            python_code=origin == "built-in" or "python" in overrides or not _is_stub(node),
        )
    return found


def builtin_functions() -> dict[str, FunctionInfo]:
    path = Path(__file__).with_name("builtins.py")
    return read_functions(path.read_text(), "built-in")


def project_functions(project: Path | None) -> dict[str, FunctionInfo]:
    """The functions of the project's `fn/*.fn` files; a file that does not parse is skipped
    (the build reports it)."""
    found: dict[str, FunctionInfo] = {}
    folder = project / "fn" if project else None
    if folder is None or not folder.is_dir():
        return found
    for file in sorted(folder.glob("*.fn")):
        try:
            found.update(read_functions(file.read_text(), f"fn/{file.name}"))
        except SyntaxError, OSError, UnicodeDecodeError:
            continue
    return found


def all_functions(project: Path | None = None) -> dict[str, FunctionInfo]:
    """Built-ins, replaced by the project's functions of the same name."""
    return {**builtin_functions(), **project_functions(project)}
