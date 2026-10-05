/** The text side of the project-function editor: names in a file, test-call arguments. */

const HEADER = /^def\s+([A-Za-z]\w*)\s*\(([^)]*)\)/gm;

/** The public functions a text defines (a `_name` is a helper), in order. */
export function functionNames(text: string): string[] {
  return [...text.matchAll(HEADER)].map((m) => m[1]);
}

const EMPTY: Record<string, string> = {
  str: '""',
  int: "0",
  float: "0",
  number: "0",
  bool: "false",
  list: "[]",
  dict: "{}",
};

/** The arguments of a test call as a JSON array text, one placeholder per required parameter
 * (by its type); optional parameters are left out. */
export function argsTemplate(text: string, name: string): string {
  const header = [...text.matchAll(HEADER)].find((m) => m[1] === name);
  if (!header) return "[]";
  const values = header[2]
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p && !p.startsWith("*") && !p.includes("="))
    .map((p) => EMPTY[p.split(":")[1]?.trim().split("[")[0] ?? ""] ?? "null");
  return `[${values.join(", ")}]`;
}

/** The array a test call passes, or why the text is not one. */
export function parseArgs(text: string): { args: unknown[] } | { error: string } {
  try {
    const parsed: unknown = JSON.parse(text);
    return Array.isArray(parsed) ? { args: parsed } : { error: "the arguments are a JSON array: [1, \"a\"]" };
  } catch (e) {
    return { error: `the arguments are not JSON: ${e instanceof Error ? e.message : e}` };
  }
}

/** A function name that can be defined (Python identifier, not private). */
export function validFunctionName(name: string): string | null {
  if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(name)) return "letters, digits and _, starting with a letter";
  return null;
}
