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

export async function chooseProject(defaultPath?: string): Promise<string | null> {
  const dir = await open({ directory: true, title: "Open a mapper project", defaultPath });
  return typeof dir === "string" ? dir : null;
}

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

export async function runMapper(project: string, command: string): Promise<CommandReport> {
  const out = await invoke<MapperOutput<CommandReport>>("mapper_command", { project, command });
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

export const mappingDelete = (project: string, name: string) =>
  reviewRequest<{ files: string[] }>({ op: "mapping_delete", project, name });

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

export async function configCheck(values: ConfigValues): Promise<ConfigIssue[]> {
  return (await configRequest<{ issues: ConfigIssue[] }>({ op: "config_check", values })).issues;
}

export async function configWrite(project: string, values: ConfigValues): Promise<void> {
  await configRequest({ op: "config_write", project, values });
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
