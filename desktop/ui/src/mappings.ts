/** A mapping's name (also its file name): letters, digits and `_`, not starting with a digit.
 * The same rule as `_IDENT` in `transpiler/model.py`. */
export const MAPPING_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Why `name` cannot be a mapping's name (`others` are the names already taken), or null. */
export function nameProblem(name: string, others: readonly string[]): string | null {
  if (!name) return "Give it a name.";
  if (!MAPPING_NAME.test(name)) return "Letters, digits and _, not starting with a digit.";
  if (others.includes(name)) return `There is already a mapping called ${name}.`;
  return null;
}
