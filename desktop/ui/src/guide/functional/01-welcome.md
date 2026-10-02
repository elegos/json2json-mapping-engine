# Welcome

This book is for people who **write and check the rules** of a mapping: what each field of the
output JSON gets from the input JSON. You work in a grid, like a spreadsheet; the tool writes the
files and a developer takes care of the code behind them. You never edit YAML.

## What a mapping is

A **mapping** turns one JSON document (the *input*) into another (the *output*). It is made of
**rules**, one for each part of the output:

| Rule | What it describes |
|---|---|
| **Field** | One value of the output: where it comes from and how it is computed. |
| **Object** | A nested object of the output, with its own rules inside. |
| **Loop** | A list in the output, built from a list in the input: its rules are applied to each element. |
| **Lookup** | A table of codes and their meaning, used by other rules. |

## Getting started

When the tool starts it shows a window with your recent projects. Open one, or create a new project
and its first mappings; the wizard button (🧙‍♂️) in the toolbar brings the window back.

```figure
{"src": "wizard.png", "alt": "The start window"}
```

## What you do here

1. Open (or create) a project, and pick a mapping from the list on the left.
2. For each field of the output, say **where** its value comes from (the *Source*) and, if it is
   not copied as it is, **how** it is computed (the *Expression*).
3. *Check* the mapping to see what is missing or wrong.
4. Look at the golden cases to see that, for a given input, the output is the one expected.

> The rest of this book follows these steps. Start with [the grid](page:functional/the-grid).
> Developers and anyone curious about what happens behind the scenes will find it in the
> [Developer book](page:developer/welcome).
