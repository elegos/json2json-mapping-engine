import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { Diagnostic, FunctionalFile, ReviewFlag } from "./model";
import type { ConfigIssue, ConfigSchema, ConfigValues } from "./projectConfig";

export interface PythonStatus {
  available: boolean;
  python?: string;
  engine?: string;
  version?: string;
  reason?: string;
}

interface MapperOutput<T> {
  json: T | null;
  stdout: string;
  stderr: string;
  code: number;
}

export interface CommandReport {
  ok: boolean;
  messages: string[];
  diagnostics: Diagnostic[];
}

export const pythonStatus = () => invoke<PythonStatus>("python_status");

export const initialProject = () => invoke<string | null>("initial_project");

export async function chooseProject(
  defaultPath?: string,
  title = "Open a mapper project",
): Promise<string | null> {
  const dir = await open({ directory: true, title, defaultPath });
  return typeof dir === "string" ? dir : null;
}

/** A fresh copy of the tutorial project in a temporary folder (the tour runs on it). */
export const tourProjectPrepare = () => invoke<string>("tour_project_prepare");

/** Deletes a copy made by `tourProjectPrepare`. */
export const tourProjectCleanup = (path: string) => invoke<void>("tour_project_cleanup", { path });

export const listFnFiles = (project: string) => invoke<string[]>("list_fn_files", { project });

export async function readFn(project: string, file: string): Promise<FunctionalFile> {
  const out = await invoke<MapperOutput<{ ok: boolean; file?: FunctionalFile; error?: string }>>(
    "read_fn",
    { project, file },
  );
  if (!out.json?.ok || !out.json.file) {
    throw new Error(out.json?.error ?? (out.stderr || `mapper exited with ${out.code}`));
  }
  return out.json.file;
}

/** Saves the tree; resolves to the ids of the rules whose validation decayed. */
export async function writeFn(
  project: string,
  file: string,
  tree: FunctionalFile,
): Promise<string[]> {
  const out = await invoke<MapperOutput<{ ok: boolean; decayed?: string[]; error?: string }>>(
    "write_fn",
    { project, file, tree: JSON.stringify({ file: tree }) },
  );
  if (!out.json?.ok) {
    throw new Error(out.json?.error ?? (out.stderr || `mapper exited with ${out.code}`));
  }
  return out.json.decayed ?? [];
}

export async function runMapper(
  project: string,
  command: string,
  allowOlder = false,
): Promise<CommandReport> {
  const out = await invoke<MapperOutput<CommandReport>>("mapper_command", {
    project,
    command,
    allowOlder,
  });
  return (
    out.json ?? {
      ok: false,
      messages: [],
      diagnostics: [
        { severity: "error", file: null, rule: null, message: out.stderr || out.stdout },
      ],
    }
  );
}

/** One edit on the tree, done by the Python worker (`mapper serve`): Target and Source
 * normalisation. Resolves to the new tree. */
export async function editTree(
  tree: FunctionalFile,
  op: "retarget" | "set_source",
  path: string,
  value: string,
): Promise<FunctionalFile> {
  const answer = await invoke<string>("edit_request", {
    request: JSON.stringify({ id: 1, op, tree, path, value }),
  });
  const parsed = JSON.parse(answer) as { ok: boolean; tree?: FunctionalFile; error?: string };
  if (!parsed.ok || !parsed.tree) throw new Error(parsed.error ?? "edit failed");
  return parsed.tree;
}

export interface CheckResult {
  diagnostics: Diagnostic[];
  review: ReviewFlag[];
}

/** Checks every rule of the tree (form, and validity against the project's schemas), and
 * reports the overrides whose auto code moved and the validated rules whose functions changed. */
export async function checkTree(
  tree: FunctionalFile,
  project: string,
  stem: string,
): Promise<CheckResult> {
  const answer = await invoke<string>("edit_request", {
    request: JSON.stringify({ id: 1, op: "check", tree, project, stem }),
  });
  const parsed = JSON.parse(answer) as {
    ok: boolean;
    diagnostics?: Diagnostic[];
    review?: ReviewFlag[];
    error?: string;
  };
  if (!parsed.ok) throw new Error(parsed.error ?? "check failed");
  return { diagnostics: parsed.diagnostics ?? [], review: parsed.review ?? [] };
}

/** One schema of a mapping, as the toolbar shows it: found and readable, missing, or broken. */
export interface SchemaStatus {
  state: "ok" | "missing" | "invalid";
  /** Where the tool looks for it, from the project root. */
  path: string;
  reason: string | null;
}

export interface SchemasStatus {
  input: SchemaStatus;
  output: SchemaStatus;
}

export type SchemaKind = "input" | "output";

export const schemasStatus = (tree: FunctionalFile, project: string, stem: string) =>
  reviewRequest<SchemasStatus>({ op: "schemas_status", tree, project, stem });

export async function chooseSchemaFile(kind: SchemaKind, defaultPath?: string): Promise<string | null> {
  const file = await open({
    title: `Load the ${kind} JSON Schema`,
    defaultPath,
    filters: [{ name: "JSON Schema", extensions: ["json"] }],
  });
  return typeof file === "string" ? file : null;
}

/** Copies a schema file into the project as the mapping's own (named by the convention). */
export const importSchema = (project: string, stem: string, kind: SchemaKind, source: string) =>
  reviewRequest<SchemaStatus>({ op: "schema_import", project, stem, kind, source });

/** The empty rules the mapping's output schema adds (one per property not covered yet).
 * With `apply` the answer also carries the tree with them in. */
export async function scaffoldRules(
  tree: FunctionalFile,
  project: string,
  stem: string,
  apply: boolean,
): Promise<{ added: number; skipped: string[]; tree?: FunctionalFile }> {
  return reviewRequest({ op: "scaffold", tree, project, stem, apply });
}

/** Creating, deleting and renaming a mapping (the files are the Python worker's business). */
/** `golden` says what becomes of cases already in `tests/golden/<name>/` (see `mappingGolden`):
 * keep them, move them to `tests/golden/<goldenTo>/`, or delete them. */
export const mappingCreate = (
  project: string,
  name: string,
  golden?: "keep" | "rename" | "delete",
  goldenTo?: string,
) => reviewRequest<{ file: string }>({ op: "mapping_create", project, name, golden, golden_to: goldenTo });

/** The golden cases a mapping of this name would find: how many files, and a free folder name. */
export const mappingGolden = (project: string, name: string) =>
  reviewRequest<{ path: string; files: number; suggest: string }>({ op: "mapping_golden", project, name });

/** What deleting the mapping removes (project-relative paths), for the confirmation. */
export const mappingRemoval = (project: string, name: string) =>
  reviewRequest<{ files: string[] }>({ op: "mapping_removal", project, name });

/** With `golden` the golden cases (`tests/golden/<name>/`) go too. */
export const mappingDelete = (project: string, name: string, golden = false) =>
  reviewRequest<{ files: string[] }>({ op: "mapping_delete", project, name, golden });

/** `fileId` sets the file's `id` (it names the PL/SQL package); without it the id follows the
 * name when it was the old name. */
export const mappingRename = (project: string, name: string, to: string, fileId?: string) =>
  reviewRequest<{ name: string; file_id: string }>({
    op: "mapping_rename",
    project,
    name,
    new: to,
    file_id: fileId,
  });

/** A golden case of a mapping and which of its optional files exist. */
export interface GoldenCase {
  name: string;
  expected: boolean;
  errors: boolean;
}

export const goldenCases = async (project: string, mapping: string) =>
  (await reviewRequest<{ cases: GoldenCase[] }>({ op: "golden_cases", project, mapping })).cases;

export async function chooseJsonFile(title: string): Promise<string | null> {
  const file = await open({ title, filters: [{ name: "JSON", extensions: ["json"] }] });
  return typeof file === "string" ? file : null;
}

/** Copies the files into `tests/golden/<mapping>/` under the standard names. */
export const goldenImport = (
  project: string,
  mapping: string,
  name: string,
  files: { input: string; expected: string | null; errors: string | null },
) => reviewRequest({ op: "golden_import", project, mapping, name, ...files });

/** What running a golden case gave. `passed` is null when the case has no expected output
 * (the output is only shown). */
export interface GoldenResult {
  name: string;
  passed: boolean | null;
  output: unknown;
  errors: GoldenError[];
  expected_errors: string[] | null;
  diff: string;
  message: string;
  /** The project's backend: the cases run on Python's whatever it is. */
  target: string;
  /** A rule called a project function that has no code for Python: it did not run, so the
   * verdict says nothing about the mapping. */
  inconclusive: boolean;
  /** Rule path -> the value the rule gave in the output (a rule inside a loop: one per element). */
  values: Record<string, unknown>;
  /** The same for the case's expected output; null when it has none. */
  expected_values: Record<string, unknown> | null;
}

/** A rule that reported an error in a run. `path` is its row in the grid (null for a `.map.py`),
 * `expected` says the case expects it to fail, `regex` that it (or a rule inside it) uses a
 * regular expression and failed because Python could not compile the pattern. */
export interface GoldenError {
  rule: string;
  cause: string;
  path: string | null;
  regex: boolean;
  expected: boolean;
  /** The project functions this rule calls that have no code for Python (it did not run). */
  unavailable: string[];
}

/** Runs cases of a mapping on the Python backend (all of them without names). The saved file of
 * the mapping is what runs. */
export const goldenRun = async (project: string, mapping: string, names?: string[]) =>
  (await reviewRequest<{ results: GoldenResult[] }>({ op: "golden_run", project, mapping, names })).results;

/** Runs the mapping on any JSON file (not a case): nothing is written, nothing is expected. */
export const inputRun = async (project: string, mapping: string, input: string) =>
  (await reviewRequest<{ result: GoldenResult }>({ op: "input_run", project, mapping, input })).result;

/** The file this mapping was last run on, kept per user outside the project (a path differs
 * from one machine to the next). */
export const inputFileGet = (project: string, mapping: string) =>
  invoke<string | null>("input_file_get", { project, mapping });

export const inputFileSet = (project: string, mapping: string, path: string | null) =>
  invoke<void>("input_file_set", { project, mapping, path });

/** The folder this user publishes the project to (kept in the app's config, not the project;
 * it beats `[publish] dir` of mapper.toml), or null for the project's own setting. */
export const publishDirGet = (project: string) =>
  invoke<string | null>("publish_dir_get", { project });

export const publishDirSet = (project: string, path: string | null) =>
  invoke<void>("publish_dir_set", { project, path });

/** What this user chose for a project in a synced folder (kept in the app's config): a local folder
 * to build in, `"-"` for "not a synced folder", or null for no choice yet. */
export const buildDirGet = (project: string) => invoke<string | null>("build_dir_get", { project });

export const buildDirSet = (project: string, path: string | null) =>
  invoke<void>("build_dir_set", { project, path });

export interface SyncedStatus {
  /** The sync provider the folder is under (OneDrive, SharePoint, Dropbox, ...), by its path. */
  synced: string | null;
  /** A git repository inside a synced folder: not supported (the sync corrupts `.git`). */
  git: string | null;
}

export const syncedStatus = (project: string) =>
  configRequest<SyncedStatus>({ op: "synced_status", project });

/** Makes the output the mapping gives now the expected result of the case. */
export const goldenRecord = (project: string, mapping: string, name: string) =>
  reviewRequest<{ output: unknown; errors: string[] }>({ op: "golden_record", project, mapping, name });

/** The text of each file of a case, as on disk (null where the file is not there). */
export const goldenRead = async (project: string, mapping: string, name: string) =>
  (
    await reviewRequest<{ files: Record<"input" | "expected" | "errors", string | null> }>({
      op: "golden_read",
      project,
      mapping,
      name,
    })
  ).files;

/** Saves one file of a case (checked first); `text` null removes it. */
export const goldenWrite = (
  project: string,
  mapping: string,
  name: string,
  role: "input" | "expected" | "errors",
  text: string | null,
) => reviewRequest({ op: "golden_write", project, mapping, name, role, text });

/** A new case holding only an input (`{}` unless given). */
export const goldenCreate = (project: string, mapping: string, name: string, text?: string) =>
  reviewRequest({ op: "golden_create", project, mapping, name, text });

export const goldenRename = (project: string, mapping: string, name: string, to: string) =>
  reviewRequest({ op: "golden_rename", project, mapping, name, new: to });

export const goldenDelete = (project: string, mapping: string, name: string) =>
  reviewRequest({ op: "golden_delete", project, mapping, name });

/** What the split pane of a rule shows. */
export interface Proposal {
  /** What the transpiler generates now from the Source and expression. */
  auto: string | null;
  /** Why it cannot (no expression and no Source, a broken expression...). */
  error: string | null;
  override: string | null;
  last_auto_version: string | null;
}

async function reviewRequest<T>(request: Record<string, unknown>): Promise<T> {
  const answer = await invoke<string>("edit_request", {
    request: JSON.stringify({ id: 1, ...request }),
  });
  const parsed = JSON.parse(answer) as { ok: boolean; error?: string } & T;
  if (!parsed.ok) throw new Error(parsed.error ?? "request failed");
  return parsed;
}

export const proposalOf = (tree: FunctionalFile, path: string) =>
  reviewRequest<Proposal>({ op: "proposal", tree, path });

/** Resolving a rule's override and validating it (one implementation, in Python):
 * `take_over` (auto -> manual), `accept_proposal` (manual -> auto), `keep_override`
 * (the auto code that moved is the new baseline), `set_override` (`code`) */
export async function reviewEdit(
  tree: FunctionalFile,
  op: "take_over" | "accept_proposal" | "keep_override" | "set_override",
  path: string,
  extra: { code?: string } = {},
): Promise<FunctionalFile> {
  return (await reviewRequest<{ tree: FunctionalFile }>({ op, tree, path, ...extra })).tree;
}

/** Adds a rule (`parent` null = document root, `index` null = last) or deletes one. */
export async function changeStructure(
  tree: FunctionalFile,
  change:
    | { op: "add_rule"; parent: string | null; index: number | null; kind: string }
    | { op: "delete_rule"; path: string },
): Promise<FunctionalFile> {
  const answer = await invoke<string>("edit_request", {
    request: JSON.stringify({ id: 1, tree, ...change }),
  });
  const parsed = JSON.parse(answer) as { ok: boolean; tree?: FunctionalFile; error?: string };
  if (!parsed.ok || !parsed.tree) throw new Error(parsed.error ?? "edit failed");
  return parsed.tree;
}

async function configRequest<T>(request: Record<string, unknown>): Promise<T> {
  const answer = await invoke<string>("edit_request", {
    request: JSON.stringify({ id: 1, ...request }),
  });
  const parsed = JSON.parse(answer) as { ok: boolean; error?: string } & T;
  if (!parsed.ok) throw new Error(parsed.error ?? "request failed");
  return parsed;
}

/** `mapper.toml` of the project: its values, and the descriptors the form is drawn from. */
export async function configRead(
  project: string,
): Promise<{ schema: ConfigSchema; values: ConfigValues }> {
  return configRequest({ op: "config_read", project });
}

/** The engine version a project declares against the tool's (`mapper.toml`, `[project] engine`):
 * `current`; `upgrade` (the tool is newer: opening moves the project up); `older` (the tool is
 * older than the project); `unversioned` (the project has none, taken like an upgrade). */
export interface EngineStatus {
  status: "current" | "upgrade" | "older" | "unversioned";
  project: string | null;
  tool: string;
}

export async function engineStatus(project: string): Promise<EngineStatus> {
  return configRequest<EngineStatus>({ op: "engine_status", project });
}

/** Writes the tool's version into the project's `mapper.toml`; never lowers it. */
export async function engineUpgrade(project: string): Promise<EngineStatus> {
  return configRequest<EngineStatus>({ op: "engine_upgrade", project });
}

/** Whether the project commits its generated files (`build/compiled`) or git ignores them (CI
 * builds them); `tracked` are the ones in the git index. `unknown`: no git, or no repository. */
export interface ArtifactsState {
  mode: "committed" | "ignored" | "unknown";
  tracked: string[];
  git: boolean;
}

export async function artifactsState(project: string): Promise<ArtifactsState> {
  return configRequest<ArtifactsState>({ op: "artifacts_state", project });
}

/** Adds `build/compiled` to `.gitignore` and stages its removal from the index (no commit). */
export async function artifactsIgnore(project: string): Promise<ArtifactsState> {
  return (await configRequest<{ before: ArtifactsState }>({ op: "artifacts_ignore", project })).before;
}

/** The opposite: no longer ignored, its files staged. */
export async function artifactsTrack(project: string): Promise<ArtifactsState> {
  return (await configRequest<{ before: ArtifactsState }>({ op: "artifacts_track", project })).before;
}

// --- version control (git mode, `cli/vcs.py`) ---------------------------------------------------

export interface VcsChange {
  path: string;
  /** git's short status: `M`, `A`, `D`, `?` (untracked)… */
  status: string;
  /** a generated file (`build/compiled`): committed with the sources, never edited */
  generated: boolean;
}

export interface VcsState {
  git: boolean;
  repo: boolean;
  branch?: string | null;
  upstream?: string | null;
  ahead?: number;
  behind?: number;
  rebasing?: boolean;
  changes?: VcsChange[];
  conflicts?: string[];
}

/** One thing both sides changed: a rule field (`rules[oid].description`), or a function. */
export interface VcsConflictItem {
  path: string;
  base: unknown;
  mine: unknown;
  remote: unknown;
  mine_missing: boolean;
  remote_missing: boolean;
}

export interface VcsConflictFile {
  file: string;
  /** `rules` (.fn.yaml), `functions` (.fn), `text` (cannot be settled here), `generated` (regenerated) */
  kind: "rules" | "functions" | "text" | "generated";
  items: VcsConflictItem[];
}

export interface VcsCommitResult {
  ok: boolean;
  committed?: boolean;
  blocked?: boolean;
  commit?: string;
  subject?: string;
  message?: string;
  problems: string[];
}

/** A request whose answer may be `ok: false` with data (a blocked commit, a pull that stopped
 * on conflicts): the answer is returned as it is, and only a failure carrying `error` throws. */
async function vcsRequest<T>(request: Record<string, unknown>): Promise<T> {
  const answer = await invoke<string>("edit_request", {
    request: JSON.stringify({ id: 1, ...request }),
  });
  const parsed = JSON.parse(answer) as { ok: boolean; error?: string; auth_required?: boolean } & T;
  if (parsed.error) {
    throw parsed.auth_required ? new VcsAuthError(parsed.error) : new Error(parsed.error);
  }
  return parsed;
}

/** The remote asked for a login the clone cannot give by itself (no `git` to run a credential
 * helper): the tool asks the user for a user name and a password or access token. */
export class VcsAuthError extends Error {}

/** What the user typed for a remote; kept in memory while the panel is open, never saved. */
export interface Credentials {
  username: string;
  password: string;
}

/** Quietly makes this clone merge mappings and functions at the rule level (a git merge driver):
 * nothing for the user to do or know. Does nothing outside a git repository. */
export const vcsEnsureDriver = (project: string) =>
  vcsRequest<{ ok: boolean; installed: boolean; changed: boolean }>({
    op: "vcs_ensure_driver",
    project,
  });

export const vcsState = (project: string) => vcsRequest<VcsState>({ op: "vcs_state", project });

export const vcsCommit = (project: string, notes: string, wip: boolean) =>
  vcsRequest<VcsCommitResult>({ op: "vcs_commit", project, notes, wip });

export const vcsPull = (project: string, credentials?: Credentials) =>
  vcsRequest<{ ok: boolean; conflicts: string[]; message?: string }>({
    op: "vcs_pull",
    project,
    credentials,
  });

export const vcsPush = (project: string, credentials?: Credentials) =>
  vcsRequest<{ ok: boolean }>({ op: "vcs_push", project, credentials });

export const vcsConflicts = async (project: string) =>
  (await vcsRequest<{ files: VcsConflictFile[] }>({ op: "vcs_conflicts", project })).files;

export const vcsResolve = (project: string, file: string, choices: Record<string, "mine" | "remote">) =>
  vcsRequest<{ ok: boolean; conflicts: string[]; done: boolean }>({
    op: "vcs_resolve",
    project,
    file,
    choices,
  });

export const vcsAbort = (project: string) => vcsRequest<{ ok: boolean }>({ op: "vcs_abort", project });

export async function configCheck(values: ConfigValues): Promise<ConfigIssue[]> {
  return (await configRequest<{ issues: ConfigIssue[] }>({ op: "config_check", values })).issues;
}

export async function configWrite(project: string, values: ConfigValues): Promise<void> {
  await configRequest({ op: "config_write", project, values });
}

export interface FunctionEntry {
  name: string;
  signature: string;
  params: { name: string; annotation: string; default: string | null; variadic: boolean }[];
  returns: string;
  doc: string;
  /** `built-in`, or the project file (`fn/text.fn`). */
  origin: string;
  builtin: boolean;
  replaces_builtin: boolean;
  targets: string[];
  /** Has code the Python backend can run (the golden cases run on it). */
  python_code: boolean;
}

/** Every function a mapping can call (built-ins and the project's own), by name. */
export async function functionList(project: string | null): Promise<FunctionEntry[]> {
  return (await configRequest<{ functions: FunctionEntry[] }>({ op: "functions", project })).functions;
}

export interface FnFile {
  /** The file name without `.fn`. */
  name: string;
  functions: string[];
  /** `builtin_overrides`: the copies of built-ins the project changed. */
  overrides: boolean;
}

export interface FnIssue {
  severity: "error" | "warning";
  line: number;
  function: string | null;
  message: string;
}

export const fnFiles = async (project: string) =>
  (await configRequest<{ files: FnFile[] }>({ op: "fn_files", project })).files;
export const fnRead = async (project: string, file: string) =>
  (await configRequest<{ text: string }>({ op: "fn_read", project, file })).text;
export const fnCheck = async (project: string, file: string, text: string) =>
  (await configRequest<{ issues: FnIssue[] }>({ op: "fn_check", project, file, text })).issues;
export const fnWrite = async (project: string, file: string, text: string) => {
  await configRequest({ op: "fn_write", project, file, text });
};
export const fnCreate = async (project: string, file: string, text?: string) => {
  await configRequest({ op: "fn_create", project, file, text });
};
export const fnDelete = async (project: string, file: string) =>
  (await configRequest<{ functions: string[] }>({ op: "fn_delete", project, file })).functions;
/** Where a project function is used: the `.fn` files and the mappings (with the calls). */
export interface RenameUse {
  files: string[];
  mappings: { name: string; calls: number }[];
}
export const fnRenamePlan = (project: string, name: string) =>
  configRequest<RenameUse>({ op: "fn_rename_plan", project, name });
/** Renames a project function in its file, the other functions and every mapping. */
export const fnRename = (project: string, name: string, next: string) =>
  configRequest<RenameUse>({ op: "fn_rename", project, name, new: next });
/** Appends a stub function (Python and the project's backend) to a file, made when missing. */
export const fnAdd = async (project: string, file: string, name: string) => {
  await configRequest({ op: "fn_add", project, file, name });
};
/** Copies a built-in into the overrides file; answers the file to edit. */
export const fnOverride = (project: string, name: string) =>
  configRequest<{ file: string; created: boolean }>({ op: "fn_override", project, name });
/** A test call on the Python backend, with the file as edited (no save needed). */
export const fnCall = (project: string, name: string, args: unknown[], text: string) =>
  configRequest<{ result?: unknown; error?: string }>({ op: "fn_call", project, name, args, text });

/** The backends and their options (what the start wizard draws its project form from). */
export const projectBackends = () => configRequest<ConfigSchema>({ op: "project_backends" });

/** Makes `project` a project for `target`: `mapper.toml` and the folders. `options` are the
 * values of the backend's section that have no default. */
export async function projectCreate(
  project: string,
  target: string,
  options: Record<string, unknown>,
): Promise<void> {
  await configRequest({ op: "project_create", project, target, options });
}

export interface CompletionItem {
  label: string;
  insert: string;
  kind: "field" | "function" | "label" | "lookup" | "alias" | "keyword" | "value";
  detail: string;
  /** A function's documentation, and where it is defined (built-in or a project file). */
  doc: string;
  origin: string;
}

/** What can be typed at `cursor` in the Target / Source / Expression cell of the rule at `path`
 * (asked of the Python worker: it knows the schemas and what `$` and `@` stand for there). */
export async function completeAt(
  tree: FunctionalFile,
  project: string,
  stem: string,
  request: { path: string; column: string; text: string; cursor: number },
): Promise<{ from: number; items: CompletionItem[] }> {
  const answer = await invoke<string>("edit_request", {
    request: JSON.stringify({ id: 1, op: "complete", tree, project, stem, ...request }),
  });
  const parsed = JSON.parse(answer) as {
    ok: boolean;
    from?: number;
    items?: CompletionItem[];
    error?: string;
  };
  if (!parsed.ok) throw new Error(parsed.error ?? "completion failed");
  return { from: parsed.from ?? request.cursor, items: parsed.items ?? [] };
}

/** A lookup kept in the project (`lookups/<label>.lookup.yaml`) and the mappings that read it. */
export interface SharedLookup {
  label: string;
  type: string | null;
  description: string | null;
  entries: Record<string, unknown>;
  used_by: string[];
}

export const sharedLookups = async (project: string) =>
  (await reviewRequest<{ lookups: SharedLookup[] }>({ op: "lookups_shared", project })).lookups;

/** Creates (`create`) or changes a project-wide lookup. Answers the mappings -> rules that went
 * back to review because the table changed. */
export const sharedLookupSave = async (
  project: string,
  table: Pick<SharedLookup, "label" | "type" | "description" | "entries">,
  create = false,
) =>
  (
    await reviewRequest<{ marked: Record<string, string[]> }>({
      op: "lookup_save",
      project,
      ...table,
      create,
    })
  ).marked;

export const sharedLookupDelete = (project: string, label: string) =>
  reviewRequest<object>({ op: "lookup_delete", project, label });

/** Moves a lookup of the (saved) mapping into the project; answers the other mappings that have
 * a lookup of the same name. */
export const sharedLookupShare = async (project: string, stem: string, label: string) =>
  (await reviewRequest<{ clashing: string[] }>({ op: "lookup_share", project, stem, label })).clashing;

/** Gives every mapping that reads the lookup its own copy and removes it from the project. */
export const sharedLookupUnshare = async (project: string, label: string) =>
  (await reviewRequest<{ changed: string[] }>({ op: "lookup_unshare", project, label })).changed;
