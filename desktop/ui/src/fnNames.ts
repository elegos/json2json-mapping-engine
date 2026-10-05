import type { CompletionItem } from "./api";

/** The names a project function can use besides its parameters and the J2JME functions. The
 * generated Python module starts with `from j2jme_runtime import *`, which gives these. */
export const FUNCTION_SCOPE: { name: string; about: string }[] = [
  {
    name: "_py",
    about:
      "Python's own built-ins: _py.len(x), _py.sum(xs), _py.sorted(xs)… Use it for any name the J2JME functions also have: inside a function, max, min, round and sum are the J2JME ones (max(items, field)), not Python's.",
  },
  { name: "re, json, operator", about: "Python modules, already imported: re.sub(…), json.dumps(…)." },
  { name: "Decimal, ROUND_HALF_UP, ROUND_DOWN", about: "From Python's decimal module, for exact arithmetic and rounding." },
  { name: "Any, Mapping", about: "Type names, for the annotations." },
];

/** Python built-ins offered after `_py.`, with a line each. */
const PY_BUILTINS: [string, string, "function" | "value"][] = [
  ["abs", "abs(x): the absolute value", "function"],
  ["all", "all(items): true when every item is true", "function"],
  ["any", "any(items): true when some item is true", "function"],
  ["bool", "bool(x): x as true / false", "function"],
  ["dict", "dict(…): a mapping", "function"],
  ["divmod", "divmod(a, b): (quotient, remainder)", "function"],
  ["enumerate", "enumerate(items): (position, item) pairs", "function"],
  ["filter", "filter(f, items): the items f accepts", "function"],
  ["float", "float(x): x as a decimal number", "function"],
  ["int", "int(x): x as a whole number", "function"],
  ["isinstance", "isinstance(x, type): x is of that type", "function"],
  ["len", "len(items): the number of items", "function"],
  ["list", "list(items): a list", "function"],
  ["map", "map(f, items): f applied to every item", "function"],
  ["max", "max(items): the greatest (Python's: no field argument)", "function"],
  ["min", "min(items): the smallest (Python's: no field argument)", "function"],
  ["range", "range(n): 0 … n-1", "function"],
  ["reversed", "reversed(items): in the opposite order", "function"],
  ["round", "round(x, n): Python's rounding (to even), not the J2JME one", "function"],
  ["set", "set(items): the distinct items", "function"],
  ["sorted", "sorted(items): a sorted list", "function"],
  ["str", "str(x): x as text", "function"],
  ["sum", "sum(items): the total (Python's: no field argument)", "function"],
  ["tuple", "tuple(items): a tuple", "function"],
  ["zip", "zip(a, b): items of a and b in pairs", "function"],
  ["None", "no value", "value"],
  ["True", "true", "value"],
  ["False", "false", "value"],
];

/** The suggestions after `_py.` that start with `partial`. */
export function pyBuiltinItems(partial: string): CompletionItem[] {
  return PY_BUILTINS.filter(([name]) => name.startsWith(partial)).map(([name, about, kind]) => ({
    label: name,
    insert: name,
    kind,
    detail: "Python",
    doc: about,
    origin: "Python built-in",
  }));
}

/** The suggestions for the names of `FUNCTION_SCOPE` (not the J2JME functions). */
export function scopeItems(partial: string): CompletionItem[] {
  return [
    ["_py", "Python's built-ins"],
    ["re", "Python's regular expressions"],
    ["json", "Python's json module"],
    ["operator", "Python's operator module"],
    ["Decimal", "exact decimal numbers"],
    ["ROUND_HALF_UP", "rounding mode of Decimal.quantize"],
    ["ROUND_DOWN", "rounding mode of Decimal.quantize"],
  ]
    .filter(([name]) => name.startsWith(partial))
    .map(([name, about]) => ({
      label: name,
      insert: name,
      kind: "value" as const,
      detail: "available in a function",
      doc: about,
      origin: "function scope",
    }));
}
