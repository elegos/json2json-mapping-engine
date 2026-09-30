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

export async function chooseProject(): Promise<string | null> {
  const dir = await open({ directory: true, title: "Open a mapper project" });
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
