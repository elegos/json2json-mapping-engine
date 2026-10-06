"""The project's functions as files (`fn/*.fn`), edited from the desktop tool (ops `fn_*` of
`mapper serve`). A file is plain typed Python read with `ast`, never imported by the tool; the
only place project code runs is the test call, in a child interpreter with a time limit.

A built-in is overridden by a function of the same name: `fn/builtin_overrides.fn` holds the
copies of the built-ins the project changed, with a warning at the top. Removing the file (or a
function from it) gives the built-in back."""

from __future__ import annotations

import ast
import contextlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from cli import shared
from cli.config import MapperConfigError, load_config
from compiler import function_registry as registry
from compiler.backends.python.backend import runtime_text
from compiler.backends.python.codegen import _project_definitions
from compiler.backends.registry import backends
from compiler.function_registry import (
    all_functions,
    builtin_functions,
    project_functions,
    read_functions,
)
from transpiler.atomic import write_atomic
from transpiler.model import FnYamlError

FN_DIR = "fn"
SUFFIX = ".fn"
OVERRIDES_FILE = "builtin_overrides.fn"
OVERRIDES_WARNING = (
    "# Built-in functions: changing them might break the mappings that call them!\n"
    "# Each function here replaces the built-in of the same name, in every mapping of the\n"
    "# project. Delete a function (or this file) to get the built-in back.\n"
)
CALL_TIMEOUT = 10
STUB_PREFIX = "NOT_IMPLEMENTED("

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def _folder(project: Path) -> Path:
    return project / FN_DIR


def _path(project: Path, name: str) -> Path:
    if not _NAME.match(name):
        raise FnYamlError(f"{name!r} is not a valid file name: letters, digits, _ and -")
    return _folder(project) / f"{name}{SUFFIX}"


def _target(project: Path) -> str:
    with contextlib.chdir(project):
        try:
            return load_config().project.target
        except MapperConfigError:
            return ""


def list_files(project: Path) -> list[dict[str, Any]]:
    """The `fn/*.fn` files with the public functions each defines."""
    files = []
    for path in sorted(_folder(project).glob(f"*{SUFFIX}")):
        try:
            names = sorted(read_functions(path.read_text(), f"fn/{path.name}"))
        except SyntaxError, UnicodeDecodeError:
            names = []
        files.append(
            {
                "name": path.stem,
                "functions": names,
                "overrides": path.name == OVERRIDES_FILE,
            }
        )
    return files


def read_file(project: Path, name: str) -> str:
    path = _path(project, name)
    if not path.is_file():
        raise FnYamlError(f"no file fn/{name}{SUFFIX} in the project")
    shared.seen(project, f"{FN_DIR}/{name}{SUFFIX}")
    return path.read_text()


def check_text(project: Path, name: str, text: str) -> list[dict[str, Any]]:
    """What is wrong with the text of a file, as the registry and the backends will read it:
    `{severity, line, function, message}`. A syntax error is the only one that stops a save."""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [
            {
                "severity": "error",
                "line": exc.lineno or 1,
                "function": None,
                "message": f"syntax error: {exc.msg}",
            }
        ]
    target = _target(project)
    builtins = builtin_functions()
    here = f"fn/{name}{SUFFIX}"
    others = {k: v for k, v in project_functions(project).items() if v.origin != here}
    issues: list[dict[str, Any]] = []

    def add(severity: str, node: ast.AST, function: str, message: str) -> None:
        issues.append(
            {
                "severity": severity,
                "line": getattr(node, "lineno", 1),
                "function": function,
                "message": message,
            }
        )

    nodes = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    known = set(backends())
    for fname, info in read_functions(text, here).items():
        node = nodes[fname]
        if fname in others:
            add("warning", node, fname, f"also defined in {others[fname].origin}: one of them wins")
        elif fname in builtins and name != OVERRIDES_FILE.removesuffix(SUFFIX):
            add("warning", node, fname, "replaces the built-in of the same name")
        if not info.doc:
            add("warning", node, fname, "no description: the first line of the docstring is shown")
        for p in info.params:
            if not p.annotation:
                add("error", node, fname, f"parameter {p.name!r} has no type")
        if not info.returns:
            add("error", node, fname, "no return type")
        for key in sorted(set(info.overrides) - known):
            add("error", node, fname, f"@override for {key!r}: not a backend of this tool")
        for key, template in sorted(info.overrides.items()):
            if template.startswith(STUB_PREFIX):
                add("error", node, fname, f"stub for {key}: write the real code")
        if not info.python_code:
            add(
                "error",
                node,
                fname,
                "no code for Python: write a body or @override(python=...) (the tool and the "
                "golden cases run Python)",
            )
        elif target and target != "python" and target not in info.overrides:
            add(
                "error",
                node,
                fname,
                f"no code for the project's backend {target!r}: add @override({target}=...)",
            )
    return issues


def write_file(project: Path, name: str, text: str) -> None:
    """Saves a file; text that does not parse is refused, so the folder always reads."""
    try:
        ast.parse(text)
    except SyntaxError as exc:
        raise FnYamlError(f"not saved, line {exc.lineno}: {exc.msg}") from exc
    path = _path(project, name)
    write_atomic(path, text)
    shared.seen(project, f"{FN_DIR}/{name}{SUFFIX}")


def _not_overrides(name: str) -> None:
    if name == OVERRIDES_FILE.removesuffix(SUFFIX):
        raise FnYamlError(f"{name} is kept for the built-in overrides")


def create_file(project: Path, name: str, text: str | None = None) -> None:
    _not_overrides(name)
    path = _path(project, name)
    if path.exists():
        raise FnYamlError(f"fn/{name}{SUFFIX} exists already")
    write_file(project, name, text if text is not None else _template(name))


def function_stub(project: Path, name: str) -> str:
    """A new function: typed, with a stub for Python (a body that raises) and for the project's
    backend (a template that calls a name no backend has), so none is forgotten."""
    target = _target(project)
    lines = []
    if target and target != "python":
        lines.append(f"@override({target}=\"{STUB_PREFIX}'{target} stub')\")")
    lines += [
        f"def {name}(value: str) -> str:",
        '    """Say what it does, in one line."""',
        '    raise NotImplementedError("python stub")',
    ]
    return "\n".join(lines) + "\n"


def add_function(project: Path, file: str, name: str) -> None:
    """Appends a stub function to `fn/<file>.fn` (made when it does not exist)."""
    if name in all_functions(project):
        raise FnYamlError(f"a function called {name!r} exists already")
    _not_overrides(file)
    path = _path(project, file)
    text = path.read_text() if path.is_file() else _template(file)
    if _target(project) not in ("", "python") and "import override" not in text:
        text = text.rstrip("\n") + "\nfrom __mapping__ import override\n"
    write_file(project, file, text.rstrip("\n") + "\n\n\n" + function_stub(project, name))


def _template(name: str) -> str:
    return (
        f"# fn/{name}.fn — functions the mappings of the project can call.\n"
        "# Typed Python; the first docstring line is the description in the explorer.\n"
        '# A body is the Python code; for another backend add @override(<target>="...").\n'
    )


def delete_file(project: Path, name: str) -> list[str]:
    """Removes the file; answers the names of the functions it defined."""
    path = _path(project, name)
    if not path.is_file():
        raise FnYamlError(f"no file fn/{name}{SUFFIX} in the project")
    gone = sorted(read_functions(path.read_text(), path.name)) if _parses(path) else []
    path.unlink()
    return gone


def _parses(path: Path) -> bool:
    try:
        ast.parse(path.read_text())
    except SyntaxError, UnicodeDecodeError:
        return False
    return True


def _builtin_copy(project: Path, name: str) -> str:
    """The source of a built-in as written in `compiler/builtins.py`, with the private helpers
    it uses, and without the `@special` marker (a project function is typed by its own
    annotations)."""
    target = _target(project)
    source = Path(registry.__file__).with_name("builtins.py").read_text()
    tree = ast.parse(source)
    defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    if name not in defs:
        raise FnYamlError(f"{name!r} is not a built-in function")
    wanted, pending = [], [name]
    while pending:
        current = pending.pop(0)
        if current in wanted:
            continue
        wanted.append(current)
        for sub in ast.walk(defs[current]):
            if isinstance(sub, ast.Name) and sub.id in defs and sub.id.startswith("_"):
                pending.append(sub.id)
    parts = []
    for fname in reversed(wanted):
        node = defs[fname]
        node.decorator_list = [
            d for d in node.decorator_list if not (isinstance(d, ast.Name) and d.id == "special")
        ]
        notes = []
        if fname == name:
            decorators, notes = _backend_overrides(name, target)
            node.decorator_list = [*decorators, *node.decorator_list]
        parts.append("".join(f"{n}\n" for n in notes) + ast.unparse(node))
    return "\n\n\n".join(parts) + "\n"


def _backend_overrides(name: str, target: str) -> tuple[list[ast.expr], list[str]]:
    """What each backend (but Python, which runs the body) writes for the built-in, as
    `@override(<backend>="...")` decorators with the parameters as `{name}`; and notes for the
    ones that cannot be shown that way. The project's own backend always gets one: a stub when
    the backend has no template to show (an aggregate it lowers to a loop, say)."""
    info = builtin_functions()[name]
    names = [p.name for p in info.params if not p.variadic]
    decorators: list[ast.expr] = []
    notes: list[str] = []
    for backend_name, backend in sorted(backends().items()):
        impl = backend.builtin_implementations().get(name)
        template = impl.target_templates.get(backend_name) if impl else None
        if template is None:
            continue
        shown = [f"{{{n}}}" for n in names]
        try:
            text = template.format(*shown) if isinstance(template, str) else template(shown)
        except Exception:  # noqa: BLE001 - a renderer of its own kind: shown as a note
            text = None
        if text is None or any(p.variadic for p in info.params):
            notes.append(
                f'# {backend_name}: written by the backend; add @override({backend_name}="...")'
            )
            continue
        call = ast.Call(
            func=ast.Name("override", ast.Load()),
            args=[],
            keywords=[ast.keyword(backend_name, ast.Constant(text))],
        )
        decorators.append(call)
    if name in ("max", "min", "sum", "avg") and target and target != "python":
        notes.append(
            f"# {target}: the backend lowers this to a loop; to change it write an expression of "
            "the parameters, calling a function you deploy, e.g."
        )
        notes.append(f'# @override({target}="MY_PKG.{name}_of({{items}}, {{field}})")')
    shown = {k.arg for d in decorators if isinstance(d, ast.Call) for k in d.keywords}
    if target and target != "python" and target not in shown:
        stub = f"{STUB_PREFIX}'{target} stub')"
        decorators.append(
            ast.Call(
                func=ast.Name("override", ast.Load()),
                args=[],
                keywords=[ast.keyword(target, ast.Constant(stub))],
            )
        )
    return decorators, notes


def override_builtin(project: Path, name: str) -> dict[str, Any]:
    """Copies a built-in into `fn/builtin_overrides.fn` (made with its warning when missing) and
    answers the file to edit. A function already overridden is left as it is."""
    path = _path(project, OVERRIDES_FILE.removesuffix(SUFFIX))
    existing = path.read_text() if path.is_file() else OVERRIDES_WARNING
    if name in read_functions(existing, path.name):
        return {"file": path.stem, "created": False}
    copy = _builtin_copy(project, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing.rstrip("\n") + "\n\n\n" + copy)
    return {"file": path.stem, "created": True}


_RUNNER = """
import json, sys
from j2jme_runtime import *
{definitions}

try:
    result = {name}(*json.loads(sys.argv[1]))
    print(json.dumps({{"ok": True, "result": result}}, ensure_ascii=False, default=str))
except Exception as exc:
    print(json.dumps({{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}}))
"""


def call_function(project: Path, name: str, args: list[Any], text: str | None = None) -> dict:
    """Runs a project function on the Python backend with `args`. `text` is the file being
    edited, used instead of what is on disk (a test call needs no save)."""
    functions = project_functions(project)
    if text is not None:
        try:
            functions.update(read_functions(text, "edited"))
        except SyntaxError as exc:
            raise FnYamlError(f"line {exc.lineno}: syntax error: {exc.msg}") from exc
    if name not in functions:
        raise FnYamlError(f"no project function called {name!r}")
    definitions, missing = _project_definitions(ast.parse(f"{name}()"), functions)
    if missing:
        raise FnYamlError(f"no code for Python in {', '.join(sorted(missing))}")
    source = _RUNNER.format(definitions="\n\n".join(ast.unparse(d) for d in definitions), name=name)
    with tempfile.TemporaryDirectory(prefix="j2jme-call-") as folder:
        (Path(folder) / "j2jme_runtime.py").write_text(runtime_text())
        try:
            done = subprocess.run(
                [sys.executable, "-c", source, json.dumps(args)],
                cwd=folder,
                env={"PYTHONPATH": folder},
                capture_output=True,
                text=True,
                timeout=CALL_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"no answer after {CALL_TIMEOUT} seconds"}
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except IndexError, ValueError:
        return {"ok": False, "error": (done.stderr or done.stdout).strip() or "no output"}
