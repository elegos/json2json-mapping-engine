# The grid

Each row is a rule. Rows inside an object or a loop are indented under it, and can be folded.

```figure
{
 "src": "grid.png",
 "alt": "The rule grid of a mapping",
 "callouts": [
  {
   "n": 1,
   "x": 0.6,
   "y": 9.7,
   "w": 11.5,
   "h": 11.0,
   "text": "The mapping list and its buttons: project properties, new mapping; the open mapping can be renamed (\u270e) or deleted (\u2715)."
  },
  {
   "n": 2,
   "x": 12.8,
   "y": 9.7,
   "w": 16.7,
   "h": 2.7,
   "text": "The views of a mapping: rules, lookups, paths and golden cases."
  },
  {
   "n": 3,
   "x": 15.8,
   "y": 18.5,
   "w": 11.7,
   "h": 61.8,
   "text": "Target: the field of the output this row fills.",
   "at": {
    "x": 21.5,
    "y": 87.4
   }
  },
  {
   "n": 4,
   "x": 42.2,
   "y": 18.5,
   "w": 11.7,
   "h": 61.8,
   "text": "Source: where the value comes from in the input.",
   "at": {
    "x": 47.8,
    "y": 87.4
   }
  },
  {
   "n": 5,
   "x": 54.4,
   "y": 18.5,
   "w": 16.4,
   "h": 61.8,
   "text": "Expression: how it is computed, when it is not a plain copy.",
   "at": {
    "x": 62.5,
    "y": 87.4
   }
  },
  {
   "n": 6,
   "x": 83.0,
   "y": 13.0,
   "w": 16.2,
   "h": 3.8,
   "text": "The schemas of the mapping; green means it is found and readable."
  },
  {
   "n": 7,
   "x": 80.3,
   "y": 5.1,
   "w": 16.1,
   "h": 2.9,
   "text": "Save writes the file; Check reports what is missing or wrong. (Developer mode adds Transpile and Build.)"
  }
 ]
}
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
