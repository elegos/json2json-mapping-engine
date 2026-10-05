# Build, check and test

The toolbar runs the `mapper` command of the project. **Transpile** and **Build** appear only in
**Developer mode**; **Check** is always there.


| Button | What it does |
|---|---|
| **Transpile** | `.fn.yaml` → `.map.py` in `build/transpiled/`. |
| **Build** | Transpiles and compiles to the backend's code in `build/`. |
| **Check** | Verifies that what is committed matches the sources, without changing them. |

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
