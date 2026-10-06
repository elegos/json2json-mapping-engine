"""What two edits of one file leave to choose, and the file once they are chosen: the part of the
merge that the git panel (`cli/vcs.py`) and the shared-folder mode (`cli/shared.py`) have in
common. `remote` is the version somebody else wrote (git: the branch pulled; shared folder: what is
on disk), `mine` the one this tool has; the engine calls them ours and theirs, the other way round.
"""

from __future__ import annotations

from typing import Any

from transpiler.merge import MergeError, load_raw, merge3, merge_fn_texts, merge_texts


class Unsettled(Exception):
    """A file that cannot be settled here, or a choice still missing."""


def kind_of(rel: str) -> str:
    """`rules` (`.fn.yaml`), `functions` (`.fn`) or `text` (the tool cannot merge it)."""
    if rel.endswith(".fn.yaml"):
        return "rules"
    return "functions" if rel.endswith(".fn") else "text"


def items(rel: str, base: str, remote: str, mine: str) -> tuple[str, list[dict[str, Any]]]:
    """`(kind, items)`: an item is `{path, base, mine, remote, mine_missing, remote_missing}`, a rule
    field, a rule or a function that both sides changed. No items: the merge settles by itself."""
    kind = kind_of(rel)
    try:
        if kind == "rules":
            result = merge3(
                load_raw(base, "base") if base.strip() else None,
                load_raw(remote, "remote"),
                load_raw(mine, "mine"),
            )
            found = result.conflicts
        elif kind == "functions":
            _, found = merge_fn_texts(base, remote, mine)
        else:
            found = []
    except MergeError:
        return "text", []
    return kind, [
        {
            "path": c.path,
            "base": c.base,
            "mine": c.theirs,
            "remote": c.ours,
            "mine_missing": c.theirs_missing,
            "remote_missing": c.ours_missing,
        }
        for c in found
    ]


def settle(rel: str, base: str, remote: str, mine: str, choices: dict[str, str]) -> str:
    """The merged text with `choices` (path -> `mine` | `remote`). Raises `Unsettled`."""
    merge_choices: Any = {p: ("theirs" if c == "mine" else "ours") for p, c in choices.items()}
    try:
        if rel.endswith(".fn.yaml"):
            text, left = merge_texts(base, remote, mine, merge_choices)
        elif rel.endswith(".fn"):
            text, left = merge_fn_texts(base, remote, mine, merge_choices)
        else:
            raise Unsettled(f"{rel} is not a file the tool can settle: edit it, or abort")
    except MergeError as exc:
        raise Unsettled(f"{rel}: {exc}") from exc
    if left:
        raise Unsettled(f"{rel}: still to choose: {', '.join(c.path for c in left)}")
    return text
