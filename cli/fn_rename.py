"""Renaming a project function (ops `fn_rename_plan` / `fn_rename` of `mapper serve`): its `def`,
the calls in the project's other functions, and the calls in the expressions, guards, filters and
code overrides of every mapping. Nothing is changed when any file cannot be rewritten.

A pure rename does not touch the validation of a rule: what it computes does not change. A manual
rule whose auto code was up to date stays up to date (its remembered auto code is renamed too)."""

from __future__ import annotations

import ast
import keyword
import re
from pathlib import Path

from compiler.function_registry import all_functions, builtin_functions, project_functions
from transpiler import review as rv
from transpiler.model import (
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LoopRule,
    ObjectRule,
    load_functional_file,
)
from transpiler.serialize import write_functional
from transpiler.shared_lookups import _walk, mapping_files

_QUOTED = re.compile(r"""('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")""")


def rename_calls(text: str, old: str, new: str) -> tuple[str, int]:
    """`text` (an expression of a mapping) with the calls of `old` renamed, and how many. A call
    is the name followed by `(` and not preceded by `.`, `$` or `@`; text in quotes is left alone."""
    pattern = re.compile(rf"(?<![\w.$@]){re.escape(old)}(?=\s*\()")
    parts = _QUOTED.split(text)
    count = 0
    for i in range(0, len(parts), 2):
        parts[i], n = pattern.subn(new, parts[i])
        count += n
    return "".join(parts), count


def _rename_in_python(text: str, old: str, new: str) -> tuple[str, int]:
    """A `.fn` file with `def old` and the calls `old(...)` renamed (by position, with `ast`)."""
    lines = text.splitlines(keepends=True)
    spots: list[tuple[int, int]] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == old:
            col = lines[node.lineno - 1].index(f"def {old}") + 4
            spots.append((node.lineno - 1, col))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == old:
            row = node.func.lineno - 1
            # `col_offset` counts UTF-8 bytes; the text is edited by characters
            spots.append((row, len(lines[row].encode()[: node.func.col_offset].decode())))
    for row, col in sorted(spots, reverse=True):
        lines[row] = lines[row][:col] + new + lines[row][col + len(old) :]
    return "".join(lines), len(spots)


def _rewrite_rule_texts(file: FunctionalFile, old: str, new: str) -> tuple[FunctionalFile, int]:
    """The file with `old` renamed in every text a rule holds; and how many calls."""
    total = 0
    renamed = []
    for rule in _walk(file.rules):
        changes: dict[str, object] = {}
        if isinstance(rule, FieldRule):
            texts = {
                "source_path": rule.source_path,
                "transform.expression": rule.transform.expression,
                "transform.code_override": rule.transform.code_override,
            }
        elif isinstance(rule, ObjectRule):
            texts = {"source": rule.source, "guard": rule.guard}
        elif isinstance(rule, LoopRule):
            texts = {"source": rule.source, "filter": rule.filter, "order_by": rule.order_by}
        else:
            continue
        for key, value in texts.items():
            if isinstance(value, str):
                text, n = rename_calls(value, old, new)
                if n:
                    changes[key] = text
                    total += n
        if changes:
            renamed.append((rule, changes))
    return _apply(file, renamed), total


def _apply(file: FunctionalFile, renamed: list) -> FunctionalFile:
    # the rules are objects of the (freshly loaded) file: change them in place
    for rule, changes in renamed:
        for key, text in changes.items():
            if key.startswith("transform."):
                setattr(rule.transform, key.split(".", 1)[1], text)
            else:
                setattr(rule, key, text)
    return file


def _check(project: Path, old: str, new: str) -> None:
    if old not in project_functions(project):
        raise FnYamlError(f"{old!r} is not a function of the project")
    if old in builtin_functions():
        raise FnYamlError(f"{old!r} replaces a built-in: delete it to get the built-in back")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", new) or keyword.iskeyword(new):
        raise FnYamlError(f"{new!r} is not a valid function name")
    if new in all_functions(project):
        raise FnYamlError(f"a function called {new!r} exists already")


def _function_files(project: Path) -> list[Path]:
    return sorted((project / "fn").glob("*.fn"))


def rename_plan(project: Path, old: str) -> dict[str, list]:
    """Where `old` is used: the `.fn` files (names) and the mappings (name, number of calls)."""
    files = []
    for path in _function_files(project):
        try:
            if _rename_in_python(path.read_text(), old, "\0")[1]:
                files.append(path.stem)
        except SyntaxError:
            continue
    mappings = []
    for path in mapping_files(project):
        try:
            _, n = _rewrite_rule_texts(load_functional_file(path), old, "\0")
        except FnYamlError:
            continue
        if n:
            mappings.append({"name": path.name.removesuffix(".fn.yaml"), "calls": n})
    return {"files": files, "mappings": mappings}


def rename_function(project: Path, old: str, new: str) -> dict[str, list]:
    """Renames `old` to `new` everywhere; answers what was changed (as `rename_plan`)."""
    _check(project, old, new)
    texts: dict[Path, str] = {}
    files: list[str] = []
    for path in _function_files(project):
        try:
            text, n = _rename_in_python(path.read_text(), old, new)
        except SyntaxError as exc:
            raise FnYamlError(
                f"{path.name} does not parse (line {exc.lineno}): fix it first"
            ) from exc
        if n:
            texts[path] = text
            files.append(path.stem)
    rewritten: dict[Path, FunctionalFile] = {}
    mappings = []
    for path in mapping_files(project):
        try:
            before = load_functional_file(path)
            proposals = rv.proposals_by_path(before)[0]
            file, n = _rewrite_rule_texts(load_functional_file(path), old, new)
        except FnYamlError:
            continue  # a mapping that does not load reports itself
        if not n:
            continue
        _keep_manual_rules_current(file, proposals)
        rewritten[path] = file
        mappings.append({"name": path.name.removesuffix(".fn.yaml"), "calls": n})
    for path, text in texts.items():
        path.write_text(text)
    for path, file in rewritten.items():
        write_functional(path, file)
    return {"files": files, "mappings": mappings}


def _keep_manual_rules_current(file: FunctionalFile, before: dict[str, str]) -> None:
    """A manual rule whose auto code was current stays current: the proposal is now the renamed one."""
    proposals = rv.proposals_by_path(file)[0]
    for path, rule in rv._with_paths(file.rules):
        if not isinstance(rule, FieldRule) or rule.transform.status != "manual":
            continue
        if before.get(path) == rule.transform.last_auto_version and path in proposals:
            rule.transform.last_auto_version = proposals[path]
