# Welcome, developers

This book is for those who **keep the machinery behind the mappings**: the functions the
expressions call, the code written by hand for rules that need it, the project settings, the
build and the tests.

## How it fits together

```
Functional file (.fn.yaml)
  → Transpiler (Python) → .map.py
    → Compiler (Python) → target code (PL/SQL)
```

The `.fn.yaml` file is the **only source of truth**: the tool writes it from the grid. The
`.map.py` and the generated code are build products, not edited by hand.

## In this book

- [Developer mode and overrides](page:developer/overrides): the code of a single rule, by hand.
- [Functions](page:developer/functions): the built-ins and your own.
- [Writing functions and overrides](page:developer/writing-functions): step by step, with a summary.
- [Project settings and backends](page:developer/project).
- [Build, check and test](page:developer/build).
- [The developer tour, step by step](page:developer/tour): a picture of each step.

The functional users' view is in the [Functional book](page:functional/welcome).
