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

Click one to pick a schema file; it is copied into the project's `schemas` folder under the name
of the mapping.

## A schema that changed

If the schema file is changed outside the tool while the mapping is open, the tool does not notice:
reopen the mapping.
