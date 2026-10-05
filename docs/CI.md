# Running `mapper` in CI

How a project that uses the engine builds, checks and deploys its mappings from a CI/CD pipeline
(GitHub Actions or Forgejo Actions), without installing Python or the desktop tool on the runner.

The jobs below are **examples** for a fictional project, `acme-mappings`: names, hosts and the
deploy step are made up; adapt them. What is real is `mapper`, `install-mapper.sh`, the manifest
and the release files described here.

- [The two ways to keep the generated artifacts](#the-two-ways-to-keep-the-generated-artifacts)
- [The manifest](#the-manifest)
- [Getting `mapper` onto the runner](#getting-mapper-onto-the-runner)
- [Example: artifacts committed, CI checks them](#example-artifacts-committed-ci-checks-them)
- [Example: artifacts not committed, CI builds and deploys](#example-artifacts-not-committed-ci-builds-and-deploys)
- [Upgrading the engine](#upgrading-the-engine)
- [Private repositories and draft releases](#private-repositories-and-draft-releases)
- [What does not exist yet](#what-does-not-exist-yet)

## The two ways to keep the generated artifacts

`mapper build` writes the deployable files (for PL/SQL, one package per mapping) and a
`manifest.json` into `build/compiled/`. A project chooses, once, what to do with that folder:

| | **Committed** (the default) | **Not committed** (`build/compiled` in `.gitignore`) |
|---|---|---|
| In the repository | sources **and** `build/compiled/*` | sources only |
| Who generates | the developer, with the tool or `mapper build`, in the same commit as the sources | CI, on every run |
| Reviewing | the generated SQL shows up in the diff | the SQL does not |
| What CI does | `mapper check`: regenerate and **fail if it differs** from the committed files | `mapper build`, then deploy |
| Risk it removes | deploying code generated from older sources | the same, by never storing it |
| Engine version known from | `[project] engine` in `mapper.toml` | the same |

`mapper check` knows which way a project works: if git ignores `build/compiled` it only builds (the
mappings must compile) and never complains about missing files; otherwise it compares.

## The manifest

`build/compiled/manifest.json` records what produced the artifacts:

```json
{
  "manifest": 1,
  "target": "plsql",
  "sources": { "mapper.toml": "ab12…", "mappings/functional/orders.fn.yaml": "cd34…",
               "schemas/orders_input.schema.json": "…", "fn/text.fn": "…" },
  "outputs": { "j2jme_functions.sql": "ef56…", "j2jme_map_orders.sql": "…" }
}
```

- The version of the engine is **not** in the manifest but in `mapper.toml`
  (`[project] engine = "0.5.0"`, written by the tool; see [the engine version](#the-engine-version-of-a-project)).
  The output is deterministic only for the same sources **and** the same engine version, so CI runs
  exactly that engine. `mapper.toml` is one of the `sources`, so an upgrade shows as a changed source.
- `sources` are hashes of `mapper.toml`, the mappings (`.fn.yaml` and `.map.py`), the schemas, the
  shared lookups and the project's `fn/*.fn`; `outputs` are hashes of each generated file. A line
  ending of CRLF counts as LF, so a Windows checkout hashes the same.
- There is no date and no machine in it: building twice from the same sources writes the same file,
  so it can be committed and compared.

What `mapper check` reports (exit code 1 when there is a problem):

| Finding | Result |
|---|---|
| a generated file missing, stale, or different from what the sources give | problem |
| a source or output in the manifest that is new, gone or changed | problem |
| no readable `manifest.json` | problem |

## The engine version of a project

`[project] engine` in `mapper.toml` is the version of the tool that last opened the project. The
desktop tool and `mapper` compare it with their own:

- a **newer** tool warns that the project will be updated, and the desktop tool then writes its
  version into `mapper.toml` (`mapper upgrade` does the same from a terminal); the generated files
  and the manifest change with the next `mapper build`, so commit them together;
- an **older** tool does not open the project (`mapper` refuses with an error), unless you accept
  the risk of incompatibility: a tick-box in the desktop tool, `--allow-older-engine` (or
  `J2JME_ALLOW_OLDER_ENGINE=1`) on the command line. `mapper.toml` is never moved back.

CI is not an "older tool" by accident: `install-mapper.sh` reads this very key, so the job runs
the version the project declares.

## Getting `mapper` onto the runner

Each release carries two files besides the desktop packages:

- `j2jme-cli-linux-x86_64.tar.gz` (and its `.sha256`): `mapper` alone, with its own Python and
  engine (about 34 MB). Nothing else needs to be installed on the runner.
- `install-mapper.sh`: installs the `mapper` of the right version and puts it in the `PATH`.

The script (needs `sh`, `curl`, `tar`, `sha256sum`):

```sh
sh install-mapper.sh                       # version = [project] engine in ./mapper.toml
sh install-mapper.sh --version 0.5.0       # or say it
sh install-mapper.sh --config other/mapper.toml --dir /opt/j2jme
```

It downloads `<releases>/v<version>/j2jme-cli-linux-x86_64.tar.gz`, checks the checksum, unpacks it
in `~/.local/share/j2jme/<version>` (`--dir` or `J2JME_HOME`; a version already there is reused, so
a cache of that folder makes the step instant) and adds its `bin/` to `$GITHUB_PATH`, which both
GitHub and Forgejo Actions read, so the **next steps** find `mapper`. Outside CI it prints the
`export PATH=…` line instead.

`<releases>` is the download address of the repository that publishes the releases, the same shape
on both platforms: `https://<host>/<owner>/<repo>/releases/download`. Give it with
`--releases` or the `J2JME_RELEASES_URL` environment variable. Keep it in a repository variable
(`vars.J2JME_RELEASES_URL`) so that workflows are the same everywhere.

The script has to be in the job's checkout: **copy `install-mapper.sh` into the project once**
(for instance `ci/install-mapper.sh`, from any release). It only downloads, checks and unpacks
an archive.

## Example: artifacts committed, CI checks them

A pull request must not be able to change a mapping without regenerating the SQL. Fictional
project `acme-mappings`, artifacts committed.

GitHub — `.github/workflows/mappings.yml`:

```yaml
name: Mappings

on:
  push:
  pull_request:

jobs:
  check:
    name: Generated files match the sources
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # the version is read from [project] engine in mapper.toml
      - name: Install mapper
        run: sh ci/install-mapper.sh
        env:
          J2JME_RELEASES_URL: ${{ vars.J2JME_RELEASES_URL }}

      - name: Check the generated files
        run: mapper check
```

Forgejo — `.forgejo/workflows/mappings.yml`. The job container has no `git` and no `curl` unless
the image brings them, and `mapper check` uses `git` to tell whether the artifacts are ignored:

```yaml
name: Mappings

on:
  push:
  pull_request:

jobs:
  check:
    name: Generated files match the sources
    runs-on: docker
    container:
      image: debian:stable-slim
    steps:
      # the JavaScript action below runs inside the job container
      - name: Tools
        run: |
          apt-get update
          apt-get install -y --no-install-recommends nodejs git curl ca-certificates
          rm -rf /var/lib/apt/lists/*

      - uses: actions/checkout@v4

      - name: Install mapper
        run: sh ci/install-mapper.sh
        env:
          J2JME_RELEASES_URL: ${{ vars.J2JME_RELEASES_URL }}

      - name: Check the generated files
        run: mapper check
```

On a failure the log lists what is wrong (`out of sync: build/compiled/…`,
`manifest: source fn/text.fn is not in it`) and ends with ``run `mapper build` ``: the developer
regenerates, commits the sources and the artifacts together, and pushes.

To keep two repositories' CI the same file for both platforms, the steps above are identical;
only the job's `runs-on` / `container` header differs.

## Example: artifacts not committed, CI builds and deploys

`build/compiled` is in `.gitignore`; the engine version is still the one in `mapper.toml`, so the
install step is the same as above. The deploy step is fictional — here, running the generated packages against an Oracle schema with
SQLcl; the packages have to go in dependency order: `j2jme_functions.sql` first (when present), then
the mapping packages, `j2jme_mappings.sql` (the index package, when configured) last.

GitHub — `.github/workflows/deploy.yml`:

```yaml
name: Build and deploy mappings

on:
  push:
    branches: [main]

jobs:
  deploy:
    name: Build and deploy
    runs-on: ubuntu-latest
    environment: test-db            # secrets of the target database
    steps:
      - uses: actions/checkout@v4

      - name: Install mapper
        run: sh ci/install-mapper.sh
        env:
          J2JME_RELEASES_URL: ${{ vars.J2JME_RELEASES_URL }}

      - name: Build
        run: mapper build

      - name: Keep the generated files
        uses: actions/upload-artifact@v4
        with:
          name: mapping-packages
          path: build/compiled/*

      - name: Deploy to the database
        run: |
          set -e
          files="build/compiled/j2jme_functions.sql"
          [ -f "$files" ] || files=""
          for f in build/compiled/*.sql; do
            case "$(basename "$f")" in j2jme_functions.sql|j2jme_mappings.sql) continue ;; esac
            files="$files $f"
          done
          [ ! -f build/compiled/j2jme_mappings.sql ] || files="$files build/compiled/j2jme_mappings.sql"
          for f in $files; do
            echo "deploying $f"
            sql -S "$DB_USER/$DB_PASSWORD@$DB_CONNECT" @"$f"
          done
        env:
          DB_USER: ${{ secrets.DB_USER }}
          DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
          DB_CONNECT: ${{ secrets.DB_CONNECT }}
```

Forgejo — `.forgejo/workflows/deploy.yml` (same steps; the container needs the tools and the
SQLcl client, here assumed to be in the image `registry.example.com/acme/ci-sqlcl`):

```yaml
name: Build and deploy mappings

on:
  push:
    branches: [main]

jobs:
  deploy:
    name: Build and deploy
    runs-on: docker
    container:
      image: registry.example.com/acme/ci-sqlcl:latest   # has git, curl, node and `sql`
    steps:
      - uses: actions/checkout@v4

      - name: Install mapper
        run: sh ci/install-mapper.sh
        env:
          J2JME_RELEASES_URL: ${{ vars.J2JME_RELEASES_URL }}

      - name: Build
        run: mapper build

      - name: Deploy to the database
        run: ci/deploy.sh build/compiled        # the same loop as above, kept in the project
        env:
          DB_USER: ${{ secrets.DB_USER }}
          DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
          DB_CONNECT: ${{ secrets.DB_CONNECT }}
```

Both examples assume nothing of the engine beyond `mapper build`; the database part is whatever the
project already does to deploy PL/SQL.

## Upgrading the engine

Upgrading is a commit, with the artifacts committed or not:

1. open the project with the new tool and accept the update (or run `mapper upgrade` with it): the
   new version is written into `mapper.toml`;
2. `mapper build` regenerates the files and `manifest.json`;
3. commit `mapper.toml` (and, if they are committed, the artifacts and the manifest) together.

Until then CI keeps installing the old version, read from `mapper.toml`. If the new engine writes
different SQL, `mapper check` on the old files fails after the upgrade until the artifacts are
regenerated, which is the point. A teammate with an older tool who opens the project is stopped
(or warned and asked to accept the risk), so nobody regenerates the files with an older engine
by accident.

## Private repositories and draft releases

A release made from a tag starts as a **draft**, which is not public; so does a release of a private
repository. The script then needs a token that can read the repository's releases:
`J2JME_TOKEN` (sent as `Authorization: token …`, which Forgejo and GitHub accept):

```yaml
      - name: Install mapper
        run: sh ci/install-mapper.sh
        env:
          J2JME_RELEASES_URL: ${{ vars.J2JME_RELEASES_URL }}
          J2JME_TOKEN: ${{ secrets.RELEASES_READ_TOKEN }}
```

If the release does not exist the script says which one it looked for
(`cannot download …/v0.5.0/j2jme-cli-linux-x86_64.tar.gz (is there a release v0.5.0?)`); a
pre-release is `v1.2.3-beta1`, and a build of the engine that is not a release (`0.1.0` in a
development checkout) has no archive.

## What does not exist yet

- Archives for Windows and macOS runners: only Linux x86-64.
- `mapper test` from the archive: the offline suite runs through `pytest`, which the bundled Python
  does not have (it ships only what `build`, `check` and `publish` need).
- `mapper publish` (check, build, then write the artifacts and their manifest to a folder of the
  project's choice) and the tool's action that puts the artifacts in `.gitignore`: planned
  (docs/IMPLEMENTATION_PLAN.md, M6.3b).
- A run of these examples in real pipelines: they are written from the pieces that exist and that
  were tested one by one (`mapper check`, the manifest, `install-mapper.sh` against a local
  release), not from a green run on GitHub or Forgejo.
