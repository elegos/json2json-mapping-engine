// Project-wide lookups, as the Lookups view and the status line talk about them.
import type { SharedLookup } from "./api";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** What a change to a table did to the rules that read it, for the status line. */
export function markedMessage(label: string, marked: Record<string, string[]>): string {
  const mappings = Object.keys(marked);
  const rules = mappings.reduce((n, m) => n + marked[m].length, 0);
  if (rules === 0) return `@${label} saved`;
  return (
    `@${label} saved; ${plural(rules, "rule")} in ${plural(mappings.length, "mapping")} ` +
    `(${mappings.join(", ")}) back to review, with a note saying what changed`
  );
}

/** The sentence that says who reads a project-wide table. */
export function readersText(table: Pick<SharedLookup, "used_by">): string {
  const readers = table.used_by;
  return readers.length === 0 ? "No mapping reads it yet." : `Read by ${readers.join(", ")}.`;
}

/** Whether the draft of a project-wide table differs from what is on disk. */
export function sharedChanged(
  saved: Pick<SharedLookup, "type" | "description" | "entries">,
  draft: Pick<SharedLookup, "type" | "description" | "entries">,
): boolean {
  const norm = (t: typeof saved) =>
    JSON.stringify([t.type ?? null, t.description || null, Object.entries(t.entries)]);
  return norm(saved) !== norm(draft);
}
