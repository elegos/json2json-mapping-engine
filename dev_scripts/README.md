# dev_scripts

Scripts the development reuses; add one here when a command sequence is run more than once.

| Script | What it does |
|---|---|
| `check.sh` | what CI runs offline: ruff, basedpyright (local config moved aside), pytest track1, UI types and tests |
| `oracle.sh` | clears `build/cache`, builds, runs the golden cases on a real Oracle (docker) |
