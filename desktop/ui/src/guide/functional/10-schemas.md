# Schemas

A **JSON Schema** describes a JSON document: its fields, their types, which are required. Each
mapping has two:

- the **input schema**, for the JSON the mapping reads. It feeds the suggestions for Source and
  the checks of what you write.
- the **output schema**, for the JSON the mapping produces. It lists the fields to fill, and lets
  the tool create their rules.

Both are optional, and can be loaded at any time.

## Status

Two buttons above the grid, *Input schema* and *Output schema*, each with a light:

| Light | Meaning |
|---|---|
| Green | The schema is found and readable. |
| Red | It is missing, or it is not valid JSON; the tooltip says which. |

Click one to open its menu:

- **Load from a file…** picks a schema file; it is copied into the project's `schemas` folder
  under the name of the mapping.
- **From the project** lists the other schemas already in the `schemas` folder: click one to use
  it for this mapping.
- **Lay out the rules again** (output schema only) creates the rules the schema describes that the
  mapping does not have yet. It changes and deletes nothing, and says so when there is nothing to
  add.

The menu also shows where the schema is, or why it is not loaded.

When a schema is already loaded, loading another asks first: the validated rules the new schema no
longer fits go back to review, and the tool tells how many.

## A schema that changed

If the schema file is changed outside the tool while the mapping is open, the tool looks again when
you come back to its window: the lights and the checks are updated. The rules are not touched by
this: to send back to review the ones the changed schema no longer fits, load the schema again
from the menu.
