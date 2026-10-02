import type { FunctionEntry } from "./api";

/** The functions whose name, signature or description contain every word of `query`
 * (names that start with it first). */
export function filterFunctions(all: FunctionEntry[], query: string): FunctionEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return all;
  const rank = (f: FunctionEntry) => {
    const name = f.name.toLowerCase();
    const text = `${name} ${f.signature} ${f.doc} ${f.origin}`.toLowerCase();
    if (!words.every((w) => text.includes(w))) return -1;
    return name.startsWith(words[0]) ? 0 : name.includes(words[0]) ? 1 : 2;
  };
  return all
    .map((f) => ({ f, r: rank(f) }))
    .filter((x) => x.r >= 0)
    .sort((a, b) => a.r - b.r || a.f.name.localeCompare(b.f.name))
    .map((x) => x.f);
}

/** The call to insert: `split_first(s, sep)` with the required arguments named; `first` is
 * the one to leave selected. Optional arguments are left out. */
export function callOf(f: FunctionEntry): { call: string; first?: string } {
  const required = f.params.filter((p) => p.default === null);
  const names = required.map((p) => p.name);
  return { call: `${f.name}(${names.join(", ")})`, first: names[0] };
}
