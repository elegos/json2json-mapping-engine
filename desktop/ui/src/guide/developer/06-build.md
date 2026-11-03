# Build, check and test

The toolbar runs the `mapper` command of the project. **Check…** is the button; in **Developer
mode** its caret (▼) lists the other steps, which run when picked.

| Step | What it does |
|---|---|
| **Transpile** | `.fn.yaml` → `.map.py` in `build/transpiled/`. |
| **Build** | Transpiles and compiles to the backend's code in `build/`. |
| **Check…** | Verifies that what is committed matches the sources, without changing them. |
| **Publish** | Checks and builds, then writes the files and `manifest.json` to the publish folder. |

Where Publish writes to, the build folder of a project in a synced folder, and whether the generated
files are committed are set once, in **Project properties › This machine and repository**.

The messages and the problems found appear below the grid; a problem that belongs to a rule is
marked on its row.

## Tests

From a terminal:

```sh
mapper test --offline       # offline tests, no runtime needed
mapper test --integration   # the golden cases, on the backend's runtime (a container)
mapper test                 # both
```

The golden cases are the contract shared by every backend, and are what CI runs.
