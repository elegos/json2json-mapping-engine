import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { Diagnostic, FunctionalFile } from "./model";

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

/** Checks every rule of the tree (form, and validity against the project's schemas). */
export async function checkTree(
  tree: FunctionalFile,
  project: string,
  stem: string,
): Promise<Diagnostic[]> {
  const answer = await invoke<string>("edit_request", {
    request: JSON.stringify({ id: 1, op: "check", tree, project, stem }),
  });
  const parsed = JSON.parse(answer) as { ok: boolean; diagnostics?: Diagnostic[]; error?: string };
  if (!parsed.ok) throw new Error(parsed.error ?? "check failed");
  return parsed.diagnostics ?? [];
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
