// The Rule Tree as `mapper fn read` prints it, and the pure functions the grid needs.
// No YAML here: the tree is JSON, the backend (Python) owns loading and writing.

export interface Validation {
  validated: boolean;
  needs_review: boolean;
  notes: string | null;
}

export interface Transform {
  expression: string | null;
  status: "auto" | "manual";
  code_override: string | null;
  last_auto_version: string | null;
}

interface Base {
  id: string | null;
  description: string | null;
}

export interface FieldRule extends Base {
  kind: "field";
  field: string;
  type: string;
  required: boolean;
  source_path: string | null;
  transform: Transform;
  validation: Validation;
  [extra: string]: unknown;
}

export interface ObjectRule extends Base {
  kind: "object";
  output: string;
  guard: string | null;
  rules: Rule[];
}

export interface LoopRule extends Base {
  kind: "loop";
  source: string;
  output: string;
  label: string | null;
  filter: string | null;
  rules: Rule[];
  [extra: string]: unknown;
}

export interface LookupRule extends Base {
  kind: "lookup";
  label: string;
  entries: Record<string, unknown>;
}

export type Rule = FieldRule | ObjectRule | LoopRule | LookupRule;

export interface FunctionalFile {
  name: string;
  id: string;
  rules: Rule[];
  path: string | null;
}

/** One grid row: a rule plus where it sits in the tree. */
export interface Row {
  /** `rules[0].rules[1]` — the path the loader reports in its errors. */
  path: string;
  depth: number;
  rule: Rule;
  /** For each ancestor level, whether that ancestor has later siblings (draws a `│`). */
  guides: boolean[];
  /** Last child of its parent (draws `└` instead of `├`). */
  last: boolean;
  hasChildren: boolean;
}

export function flatten(
  rules: Rule[],
  prefix = "rules",
  depth = 0,
  guides: boolean[] = [],
): Row[] {
  const rows: Row[] = [];
  rules.forEach((rule, i) => {
    const path = `${prefix}[${i}]`;
    const last = i === rules.length - 1;
    const children = rule.kind === "object" || rule.kind === "loop" ? rule.rules : [];
    rows.push({ path, depth, rule, guides, last, hasChildren: children.length > 0 });
    // the top level draws no connectors, so its children have no guide for it
    const below = depth === 0 ? guides : [...guides, !last];
    rows.push(...flatten(children, `${path}.rules`, depth + 1, below));
  });
  return rows;
}

/** The rows that are visible when the rules at `collapsed` paths are folded. */
export function visibleRows(rows: Row[], collapsed: ReadonlySet<string>): Row[] {
  return rows.filter((row) => {
    for (const path of collapsed) if (row.path.startsWith(`${path}.rules[`)) return false;
    return true;
  });
}

/** The tree drawing that precedes a Target: `│  ├ `, `   └ `; empty at the top level. */
export function treePrefix(row: Row): string {
  if (row.depth === 0) return "";
  return row.guides.map((more) => (more ? "│  " : "   ")).join("") + (row.last ? "└─ " : "├─ ");
}

/** The rule at a `rules[0].rules[1]` path, or undefined. */
export function ruleAt(file: FunctionalFile, path: string): Rule | undefined {
  const indexes = [...path.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1]));
  let rules: Rule[] = file.rules;
  let rule: Rule | undefined;
  for (const i of indexes) {
    rule = rules[i];
    if (!rule) return undefined;
    rules = rule.kind === "object" || rule.kind === "loop" ? rule.rules : [];
  }
  return rule;
}

/** What the Target column shows: a top-level field as `$.Name`, a nested one relative to its
 * parent (`Name`), a container by its stored output (`$.Lines[*]`, `@.Tax`). */
export function nameOf(rule: Rule, depth = 1): string {
  switch (rule.kind) {
    case "field":
      return depth === 0 ? `$.${rule.field}` : rule.field;
    case "lookup":
      return rule.label;
    default:
      return rule.output;
  }
}

/** Source column: a field's `source.path`, a loop's `source`. */
export function sourceOf(rule: Rule): string {
  if (rule.kind === "field") return rule.source_path ?? "";
  if (rule.kind === "loop") return rule.source;
  return "";
}

/** Expression column: a field's expression, a loop's `filter`, an object's `guard`. */
export function expressionOf(rule: Rule): string {
  if (rule.kind === "field") return rule.transform.expression ?? "";
  if (rule.kind === "loop") return rule.filter ?? "";
  if (rule.kind === "object") return rule.guard ?? "";
  return "";
}

export function setExpression(rule: Rule, value: string): void {
  if (rule.kind === "field") rule.transform.expression = value || null;
  else if (rule.kind === "loop") rule.filter = value || null;
  else if (rule.kind === "object") rule.guard = value || null;
}

export interface Diagnostic {
  severity: "error" | "warning";
  file: string | null;
  rule: string | null;
  /** Grid column id, when the checker knows it (else guessed from the message). */
  column?: string | null;
  message: string;
}

/** The column a diagnostic is about. */
export function columnOf(d: Diagnostic): string | null {
  return d.column ?? columnOfMessage(d.message);
}

/** Diagnostics for one file, keyed by rule path (the file-level ones under ""). */
export function diagnosticsByRule(
  diagnostics: Diagnostic[],
  file: string,
): Map<string, Diagnostic[]> {
  const byRule = new Map<string, Diagnostic[]>();
  for (const d of diagnostics) {
    if (d.file !== null && !file.endsWith(d.file) && !d.file.endsWith(file)) continue;
    const key = d.rule ?? "";
    byRule.set(key, [...(byRule.get(key) ?? []), d]);
  }
  return byRule;
}

export type ReviewState = "validated" | "review" | "none";

export function reviewState(rule: Rule): ReviewState {
  if (rule.kind !== "field") return "none";
  if (rule.validation.validated) return "validated";
  return rule.validation.needs_review ? "review" : "none";
}

/** Grid column a loader / checker message is about, from the key it names
 * (`'type' must be…`, `transform.status …`); null when it names none. */
export function columnOfMessage(message: string): string | null {
  const keys: [RegExp, string][] = [
    [/\b(field|output|label)\b/, "target"],
    [/\btype\b/, "type"],
    [/\brequired\b/, "req"],
    [/\bsource\b/, "source"],
    [/\b(expression|transform|code_override|filter|guard|sort|parallel)\b/, "expression"],
    [/\bdescription\b/, "description"],
    [/\bvalidation\b/, "validated"],
  ];
  const named = /'([A-Za-z_.]+)'|\b(transform\.\w+)/.exec(message)?.[0] ?? "";
  for (const [pattern, column] of keys) if (pattern.test(named)) return column;
  return null;
}

const COLUMN_LABELS: Record<string, string> = {
  target: "Target",
  type: "Type",
  req: "Req.",
  source: "Source",
  expression: "Expression / filter / guard",
  description: "Description",
  validated: "Validated",
};

/** What makes a row worth a warning sign, one line per issue (the sign's tooltip). */
export function rowIssues(rule: Rule, diagnostics: Diagnostic[]): string[] {
  const issues: string[] = [];
  for (const d of diagnostics) {
    const column = columnOf(d);
    const what = column ? `Invalid ${COLUMN_LABELS[column] ?? column}` : "Invalid rule";
    issues.push(`${d.severity === "error" ? what : "Warning"}: ${d.message}`);
  }
  if ((rule.kind === "loop" || rule.kind === "object") && rule.rules.length === 0) {
    issues.push("Empty container");
  }
  if (rule.kind === "field") {
    if (rule.validation.needs_review) issues.push("Review flag");
    else if (!rule.validation.validated) issues.push("Not validated");
  }
  return issues;
}

export const MAX_RECENT = 10;

/** `dir` moved to the front of the recent list, without duplicates, capped. */
export function pushRecent(recent: string[], dir: string): string[] {
  return [dir, ...recent.filter((d) => d !== dir)].slice(0, MAX_RECENT);
}

/** Where "add a rule" puts it, given the selected row: inside a selected container (last),
 * else right after the selected rule, else at the end of the document. */
export function insertionPoint(selected: Row | undefined): { parent: string | null; index: number | null } {
  if (!selected) return { parent: null, index: null };
  if (selected.rule.kind === "object" || selected.rule.kind === "loop") {
    return { parent: selected.path, index: null };
  }
  const match = /^(.*)\.rules\[(\d+)\]$|^rules\[(\d+)\]$/.exec(selected.path);
  if (!match) return { parent: null, index: null };
  if (match[1] !== undefined) return { parent: match[1], index: Number(match[2]) + 1 };
  return { parent: null, index: Number(match[3]) + 1 };
}

/** Number of rules below a row (0 for leaves). */
export function descendants(rule: Rule): number {
  if (rule.kind !== "object" && rule.kind !== "loop") return 0;
  return rule.rules.reduce((n, r) => n + 1 + descendants(r), 0);
}
