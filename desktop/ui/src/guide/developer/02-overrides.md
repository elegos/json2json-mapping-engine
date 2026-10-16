# Developer mode and overrides

**Developer mode** shows what a functional user does not need: the validation column, the code of
the selected rule in the override pane, and the Transpile and Build buttons. (*Show rule ids* is a
separate switch.)


```figure
{"src": "developer.png", "alt": "The grid in Developer mode, with the override pane"}
```

## Auto and manual

Each rule's code is in one of two states:

| State | Meaning |
|---|---|
| **auto** | The code is generated from the Source and the Expression at every build. |
| **manual** | You wrote the code. It is used exactly as written. |

When an operation cannot be written with the available functions, select the rule and press
**Edit as code** in the override pane: the rule becomes **manual**. The code you write is the
**developer dialect**: the Python subset directly, with `root` (the input document), `src` (the
current element of the innermost loop; `src1` is the one around it) and `index` (its position;
`index1` for the outer loop), and no `$` / `@` anchors.

### Ordering and comprehensions in the dialect

A loop's **order by** (see [Loops](page:functional/loops)) is written with `sorted`, always as the
iterable of a `for`:

```python
for index, src in enumerate(sorted(root.items, key="sku", reverse=True), start=1):
    ...
```

| Argument | Meaning |
|---|---|
| `key="field"` | Order by a field of the element. |
| `by=<expression>` | Order by an expression of the element (`by=src.qty * src.price`). |
| `kind="number"` / `"str"` | How a computed key compares; needed with `by=`, because the type of the key is not guessed. |
| `reverse=True` | Descending. |
| `nulls="first"` | The elements with no key come first (last by default, whichever the direction). |

For several keys write one call per key, the **last key innermost**: `sorted(sorted(a, key="y"), key="x")`
orders by `x`, then `y` (the sorts are stable: equal keys keep their order). `sorted` and
`enumerate` are wrappers the code generator recognizes, not functions of the registry. Typing
`sorted(` in the editor suggests the arguments.

The other forms of the cells exist in the dialect with the same meaning: comprehensions
(`count(x for x in root.items if x.qty > 1)`, `any(...)`, `all(...)`), `matches(text, "pattern")` and
`x in ("A", "B")`. A comprehension's variable completes its fields as you type (`x.`).

## When the functional side moves

If a user changes the Source or the Expression of a manual rule, the rule is flagged as **out of
date**. You then see the code you wrote next to what the tool would generate now, and choose:

1. **Use auto code**: the rule goes back to auto and your code is cleared.
2. **Keep override**: your code stays and the flag goes away; revise it if needed.

An override is never discarded silently: each flagged rule needs your decision.

## Validation

You decide when a rule is **validated**. Changes the functional users make to Source or
Expression put it back to *To review*; your own edits to the code do not, because that code is
yours.
