# Developer mode and overrides

**Developer mode** shows what a functional user does not need: the validation column, the rule
ids, and the code of each rule.


```figure
{"src": "developer.png", "alt": "The grid in Developer mode, with the override pane"}
```

## Auto and manual

Each rule's code is in one of two states:

| State | Meaning |
|---|---|
| **auto** | The code is generated from the Source and the Expression at every build. |
| **manual** | You wrote the code. It is used exactly as written. |

When an operation cannot be written with the available functions, open the rule's code and edit
it: the rule becomes **manual**. The code you write is the **developer dialect**: the Python
subset directly, with `root` (the input document), `src` (the current element), `out` and `index`,
and no `$` / `@` anchors.

## When the functional side moves

If a user changes the Source or the Expression of a manual rule, the rule is flagged as **out of
date**. You then see the code you wrote next to what the tool would generate now, and choose:

1. **Accept the new proposal**: the rule goes back to auto and your code is cleared.
2. **Keep the override**: your code stays and the flag goes away; revise it if needed.

An override is never discarded silently: each flagged rule needs your decision.

## Validation

You decide when a rule is **validated**. Changes the functional users make to Source or
Expression put it back to *To review*; your own edits to the code do not, because that code is
yours.
