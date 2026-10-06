import type { GoldenResult } from "./api";

export interface RunReport {
  /** No rule reported an error and all of them ran. */
  ok: boolean;
  label: string;
  /** One line per rule that failed, or did not run. */
  lines: string[];
  /** The grid row (`rules[0].rules[1]`) of each line, null when it has none (a `.map.py`). */
  paths: (string | null)[];
}

/** What a run of the mapping on an input says: no errors, or the rules that failed with their cause. */
export function runReport(result: GoldenResult): RunReport {
  const lines = result.errors.map((e) =>
    e.unavailable.length > 0
      ? `${e.rule}: did not run, no Python code for ${e.unavailable.join(", ")}`
      : `${e.rule}: ${e.cause}`,
  );
  const paths = result.errors.map((e) => e.path);
  if (lines.length === 0) return { ok: true, label: "No errors", lines, paths };
  return { ok: false, label: lines.length === 1 ? "1 error" : `${lines.length} errors`, lines, paths };
}
