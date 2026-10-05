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

Change it in the **Project properties** tab. If the new backend has no settings yet, it gets a section with its defaults, and the form marks the
required ones (*) for you to fill in.

## Project properties

```figure
{"src": "project.png", "alt": "The Project properties view"}
```


The tab shows every setting with a short help, and checks what you type before saving it. Comments
and the order of `mapper.toml` are kept.

`mapper.toml` also records the version of the tool that last opened the project (`engine`); it is
not a setting you edit here. A newer tool tells you that opening the project updates it to its
version; an older tool will not open it unless you tick that you accept the risk of incompatibility,
and the file is never taken back to an older version.
