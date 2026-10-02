# Project settings and backends

A project is a folder with a `mapper.toml`, and these folders:

| Folder | Content |
|---|---|
| `mappings/functional/` | The `.fn.yaml` files, one per mapping. |
| `schemas/` | The input and output JSON Schemas of the mappings. |
| `fn/` | The project's own functions. |
| `tests/golden/` | The golden cases. |

## The backend

A **backend** is the language the mappings are turned into (for example PL/SQL). The project has
**one active backend**, named in `[project] target`. Its settings are in the table
`[target.<name>]`; the tables of the other backends are kept untouched, so going back to one finds
its settings as they were.

Change it in the **Project properties** tab. If the new backend has no settings yet, it starts
from its defaults and asks for the required ones.

## Project properties

The tab shows every setting with a short help, and checks what you type before saving it. Comments
and the order of `mapper.toml` are kept.
