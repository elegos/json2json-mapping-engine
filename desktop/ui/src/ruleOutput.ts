/** The grid's Output column: what each rule gave when the mapping ran on an input, and, when the
 * input is a golden case with an expected output, where that differs. */
import type { GoldenResult } from "./api";

export type OutputState = "" | "same" | "diff";

export interface OutputCell {
  /** One line for the cell. */
  text: string;
  /** `diff`: the case expects something else here (the tooltip says what). */
  state: OutputState;
  /** The whole value, and the expected one when it differs. */
  tooltip: string;
}

const show = (v: unknown): string => (typeof v === "string" ? v : JSON.stringify(v));
const pretty = (v: unknown): string => (typeof v === "string" ? v : JSON.stringify(v, null, 2));

function equal(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  return ka.length === kb.length && ka.every((k) => k in b && equal((a as never)[k], (b as never)[k]));
}

/** What the column shows for the rule at `path`; null when there is nothing to say (no run, or the
 * rule left nothing in the output and nothing was expected). */
export function outputCell(result: GoldenResult | null, path: string): OutputCell | null {
  if (!result) return null;
  const has = path in result.values;
  const actual = result.values[path];
  const expectedAll = result.expected_values;
  if (!expectedAll) return has ? { text: show(actual), state: "", tooltip: pretty(actual) } : null;
  const expects = path in expectedAll;
  if (!has && !expects) return null;
  if (has && expects && equal(actual, expectedAll[path])) {
    return { text: show(actual), state: "same", tooltip: pretty(actual) };
  }
  return {
    text: has ? show(actual) : "(nothing)",
    state: "diff",
    tooltip: `Gave: ${has ? pretty(actual) : "nothing"}\nExpected: ${expects ? pretty(expectedAll[path]) : "nothing"}`,
  };
}

/** What the selector holds: a golden case, or a file outside the project (none: null). */
export type OutputSource = { kind: "case"; name: string } | { kind: "file"; path: string };

export const baseName = (path: string): string => path.split(/[\\/]/).pop() ?? path;

/** The selector's light: green when an input is chosen and there (a case that exists, a file that
 * was read), red when the choice is gone, off when none is chosen. */
export function outputLight(
  source: OutputSource | null,
  caseNames: string[],
  fileMissing: boolean,
): "ok" | "missing" | "unknown" {
  if (!source) return "unknown";
  if (source.kind === "case") return caseNames.includes(source.name) ? "ok" : "missing";
  return fileMissing ? "missing" : "ok";
}

/** The folder part of a path (with the separator it uses); "" when it has none. */
export const dirName = (path: string): string => {
  const at = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return at < 0 ? "" : path.slice(0, at);
};

/** Where the dialogs of the run's input and output start: the folder of the input file when there is
 * one, else the last folder an input was taken from, else the project's folder. */
export function inputDialogDir(rememberedFile: string | null, lastDir: string | null, project: string | null): string | undefined {
  return (rememberedFile && dirName(rememberedFile)) || lastDir || project || undefined;
}

/** The name proposed for the mapped JSON of a run: the input's name with `.mapped` before `.json`,
 * in the input's folder (a golden case has no file of its own: the project folder is used). */
export function mappedFilePath(source: OutputSource, project: string | null): string {
  if (source.kind === "case") return `${project ? project + "/" : ""}${source.name}.mapped.json`;
  const file = baseName(source.path).replace(/\.json$/i, "");
  const dir = dirName(source.path);
  return `${dir ? dir + "/" : ""}${file}.mapped.json`;
}
