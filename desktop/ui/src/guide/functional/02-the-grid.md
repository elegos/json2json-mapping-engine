# The grid

Each row is a rule. Rows inside an object or a loop are indented under it, and can be folded.

```figure
{"src": "grid.png", "alt": "The rule grid of a mapping",
 "callouts": [
   {"n": 1, "x": 0, "y": 8, "w": 18, "h": 80, "text": "The mappings of the project; the open one is highlighted."},
   {"n": 2, "x": 20, "y": 8, "w": 20, "h": 8, "text": "Target: the field of the output this row fills.", "at": {"x": 30, "y": 30}},
   {"n": 3, "x": 42, "y": 8, "w": 20, "h": 8, "text": "Source: where the value comes from in the input.", "at": {"x": 52, "y": 30}},
   {"n": 4, "x": 64, "y": 8, "w": 30, "h": 8, "text": "Expression: how it is computed, when it is not a plain copy.", "at": {"x": 80, "y": 30}}
 ]}
```

## Working in the grid

- Click a cell to edit it; Enter confirms, Esc cancels. Edits can be undone with **Ctrl + Z**
  and redone with **Ctrl + Y**.
- The filter field above the grid finds rows by what they contain.
- **Save** writes the file. A dot on the button means there are changes not saved yet.
- **Check** reports what is missing or wrong; the problems are marked on the rows concerned.

## The columns

- [Target](page:functional/target) — the field of the output.
- [Source](page:functional/source) — where the value comes from.
- [Expression](page:functional/expression) — how it is computed.
