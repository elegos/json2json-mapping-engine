"""Rule-level 3-way merge of `.fn.yaml` files (docs/ARCHITECTURE.md, §Version control,
§The merge engine).

Works on the raw YAML data (what `yaml.safe_load` gives), so every key of the file is kept, known
to the loader or not. A `rules` list is matched by rule id, not by position: two people editing
different rules never conflict, whatever their lines look like. Everything else is merged key by
key: a side that did not change a value yields to the other; two different changes of the same
value are a conflict.

`merge3` never raises on a conflict: it keeps *ours* there and reports the conflict, with the three
values, so the caller can ask the user (`choices`: path -> "ours" | "theirs") or give up.
"""

from __future__ import annotations

import ast
import copy
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

Side = Literal["ours", "theirs"]
_MISSING = object()


class MergeError(Exception):
    """A file that cannot be merged at rule level (not YAML, or not a mapping)."""


@dataclass
class Conflict:
    """Both sides changed the same value. `path` reads like the grid does: `rules[cust].source`,
    `rules[cust].rules[cust_name].transform.expression`. A missing side is `None` with the
    matching `*_missing` flag (a rule or key deleted on that side)."""

    path: str
    base: Any
    ours: Any
    theirs: Any
    base_missing: bool = False
    ours_missing: bool = False
    theirs_missing: bool = False


@dataclass
class MergeResult:
    data: dict[str, Any]
    conflicts: list[Conflict]

    @property
    def clean(self) -> bool:
        return not self.conflicts


def _rule_key(rule: Any) -> Any:
    """What identifies a rule across versions: its id. A rule without one (the id is only
    assigned when the file is loaded) is told apart by what it writes or reads."""
    if isinstance(rule, dict):
        if rule.get("id") is not None:
            return str(rule["id"])
        for k in ("field", "label", "output"):
            if k in rule:
                return f"~{k}:{rule[k]}"
    return None


def _keyed(items: Any) -> dict[str, Any] | None:
    """`items` as {key: rule} if it is a list of rules with distinct keys, else None."""
    if not isinstance(items, list):
        return None
    out: dict[str, Any] = {}
    for item in items:
        key = _rule_key(item)
        if key is None or key in out:
            return None
        out[key] = item
    return out


class _Merger:
    def __init__(self, choices: dict[str, Side]) -> None:
        self.choices = choices
        self.conflicts: list[Conflict] = []

    def _conflict(self, path: str, base: Any, ours: Any, theirs: Any) -> Any:
        """Record it and return the value for it: the user's choice, else ours (the key is
        dropped when the chosen side has none)."""
        c = Conflict(
            path,
            None if base is _MISSING else base,
            None if ours is _MISSING else ours,
            None if theirs is _MISSING else theirs,
            base is _MISSING,
            ours is _MISSING,
            theirs is _MISSING,
        )
        choice = self.choices.get(path)
        if choice is None:
            self.conflicts.append(c)
            return ours
        return theirs if choice == "theirs" else ours

    def value(self, path: str, base: Any, ours: Any, theirs: Any) -> Any:
        if ours == theirs:
            return ours
        if ours == base:
            return theirs
        if theirs == base:
            return ours
        if isinstance(ours, dict) and isinstance(theirs, dict):
            b = base if isinstance(base, dict) else {}
            return self.mapping(path, b, ours, theirs)
        o_keyed, t_keyed = _keyed(ours), _keyed(theirs)
        if o_keyed is not None and t_keyed is not None:
            b_keyed = _keyed(base) if base is not _MISSING else {}
            if b_keyed is None:
                b_keyed = {}
            return self.rules(path, b_keyed, o_keyed, t_keyed)
        return self._conflict(path, base, ours, theirs)

    def mapping(
        self, path: str, base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any]
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        keys = list(ours) + [k for k in theirs if k not in ours]
        keys += [k for k in base if k not in ours and k not in theirs]
        for key in keys:
            sub = f"{path}.{key}" if path else key
            merged = self.value(
                sub, base.get(key, _MISSING), ours.get(key, _MISSING), theirs.get(key, _MISSING)
            )
            if merged is not _MISSING:
                out[key] = merged
        return out

    def rules(
        self,
        path: str,
        base: dict[str, Any],
        ours: dict[str, Any],
        theirs: dict[str, Any],
    ) -> list[Any]:
        o_order, t_order, b_order = list(ours), list(theirs), list(base)
        common = [k for k in o_order if k in t_order]
        o_moved = [k for k in o_order if k in b_order] != [k for k in b_order if k in o_order]
        # the order of the side that reordered wins; with no reorder, theirs (the one pulled in)
        skeleton, other = (o_order, t_order) if o_moved or not common else (t_order, o_order)
        order = list(skeleton)
        for i, key in enumerate(other):
            if key in order:
                continue
            prev = next((k for k in reversed(other[:i]) if k in order), None)
            order.insert(0 if prev is None else order.index(prev) + 1, key)
        out: list[Any] = []
        for key in order:
            sub = f"{path}[{key}]"
            b = base.get(key, _MISSING)
            o, t = ours.get(key, _MISSING), theirs.get(key, _MISSING)
            if o is _MISSING and t is _MISSING:
                continue
            merged = self.value(sub, b, o, t)
            if merged is not _MISSING:
                out.append(merged)
        return out


def merge3(
    base: dict[str, Any] | None,
    ours: dict[str, Any],
    theirs: dict[str, Any],
    choices: dict[str, Side] | None = None,
) -> MergeResult:
    """Merge `ours` and `theirs`, both derived from `base` (None: no common ancestor, so both
    added the file: everything that differs is a conflict, rules are still matched by id)."""
    for name, d in (("ours", ours), ("theirs", theirs)):
        if not isinstance(d, dict):
            raise MergeError(f"{name}: the top level must be a mapping")
    merger = _Merger(choices or {})
    data = merger.mapping("", copy.deepcopy(base) if isinstance(base, dict) else {}, ours, theirs)
    return MergeResult(copy.deepcopy(data), merger.conflicts)


def _blocks(text: str, who: str) -> dict[str, str]:
    """A `.fn` file as {key: text}: one block per top-level statement, each with the comments and
    blank lines above it. A function or class is keyed by its name, anything else (imports,
    constants, the docstring) by its own text, so an import added on each side is kept twice
    only if it differs."""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise MergeError(f"{who}: not valid Python: {exc}") from exc
    lines = text.splitlines(keepends=True)
    out: dict[str, str] = {}
    start = 0
    for node in tree.body:
        end = node.end_lineno or node.lineno
        chunk = "".join(lines[start:end])
        start = end
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            key = node.name
        else:
            key = "~" + "".join(lines[node.lineno - 1 : end]).strip()
        n = 1
        unique = key
        while unique in out:
            n += 1
            unique = f"{key}#{n}"
        out[unique] = chunk if chunk.endswith("\n") else chunk + "\n"
    tail = "".join(lines[start:])
    if tail.strip():
        out["~tail"] = tail if tail.endswith("\n") else tail + "\n"
    return out


def merge_fn_texts(
    base: str, ours: str, theirs: str, choices: dict[str, Side] | None = None
) -> tuple[str, list[Conflict]]:
    """Merge three versions of a `fn/*.fn` file function by function (docs/ARCHITECTURE.md,
    §The merge engine): a function changed on one side only, added or deleted, merges; the same
    function changed differently on both sides is a conflict (`functions[name]`), with ours kept.
    `choices` settle a conflict by path, as in `merge3`.
    Raises `MergeError` if one of the versions is not Python."""
    merger = _Merger(choices or {})
    b = _blocks(base, "base") if base.strip() else {}
    merged = merger.rules("functions", b, _blocks(ours, "ours"), _blocks(theirs, "theirs"))
    return "".join(merged), merger.conflicts


def load_raw(text: str, who: str) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MergeError(f"{who}: not valid YAML: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise MergeError(f"{who}: the top level must be a mapping")
    return raw


def dump_raw(data: dict[str, Any]) -> str:
    """Same YAML dialect as `transpiler.serialize.functional_to_yaml`."""
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def merge_texts(
    base: str, ours: str, theirs: str, choices: dict[str, Side] | None = None
) -> tuple[str, list[Conflict]]:
    """Merge three versions of a file given as text. Raises `MergeError` if one is not YAML."""
    result = merge3(
        load_raw(base, "base") if base.strip() else None,
        load_raw(ours, "ours"),
        load_raw(theirs, "theirs"),
        choices,
    )
    return dump_raw(result.data), result.conflicts


def text_merge(base: str, ours: str, theirs: str) -> tuple[str, bool]:
    """Standard line-based 3-way merge (`git merge-file`), with conflict markers. Returns
    `(text, clean)`. The fallback for a file that is not YAML, or whose conflicts the user has
    to settle in an editor. Raises `MergeError` when git is not there."""
    with tempfile.TemporaryDirectory() as tmp:
        files = {}
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            files[name] = Path(tmp) / name
            files[name].write_text(text)
        try:
            proc = subprocess.run(
                ["git", "merge-file", "-p", "-L", "ours", "-L", "base", "-L", "theirs"]
                + [str(files[n]) for n in ("ours", "base", "theirs")],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MergeError("git is not installed: no text-level merge") from exc
    if proc.returncode < 0 or proc.returncode > 127:
        raise MergeError(f"git merge-file failed: {proc.stderr.strip()}")
    return proc.stdout, proc.returncode == 0
