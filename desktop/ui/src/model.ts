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
  /** A constant Source (`27`, `"text"`, `true`, `null`); only meaningful when `has_constant`. */
  source_constant: unknown;
  has_constant: boolean;
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
  /** Primitive type every value must have; null = not declared. */
  type: string | null;
}

export type Rule = FieldRule | ObjectRule | LoopRule | LookupRule;

/** The `paths:` section: what `$` means and the named path aliases (all from the real root). */
export interface PathsSection {
  root: string | null;
  aliases: Record<string, string>;
}

export interface FunctionalFile {
  name: string;
  id: string;
  rules: Rule[];
  path: string | null;
  paths: PathsSection;
}

/** `aliases` plus a new one with a free name (`alias`, `alias2`, …). */
export function addAlias(aliases: Record<string, string>): Record<string, string> {
  let name = "alias";
  for (let n = 2; name in aliases; n++) name = `alias${n}`;
  return { ...aliases, [name]: "$." };
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
export function nameOf(rule: Rule): string {
  switch (rule.kind) {
    case "field":
      return rule.field;
    case "lookup":
      return rule.label;
    default:
      // `$.Lines[*]` / `@.Tax` are written `Lines[*]` / `Tax`: the prefix is only noise
      return rule.output.replace(/^[$@]\.?/, "");
  }
}

/** Source column: a field's `source.path`, a loop's `source`. */
export function sourceOf(rule: Rule): string {
  if (rule.kind === "field") {
    return rule.has_constant ? JSON.stringify(rule.source_constant) : (rule.source_path ?? "");
  }
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

/** Where a rule in `saved` is: by id when it has one (survives inserts and deletes), else by path. */
export function savedIndex(saved: Rule[]): { byId: Map<string, Rule>; byPath: Map<string, Rule> } {
  const byId = new Map<string, Rule>();
  const byPath = new Map<string, Rule>();
  for (const row of flatten(saved)) {
    byPath.set(row.path, row.rule);
    if (row.rule.id) byId.set(row.rule.id, row.rule);
  }
  return { byId, byPath };
}

/**
 * Grid columns (colId) whose value differs from the saved rule; "*" = the rule is new.
 * Used to show unsaved edits in bold.
 */
export function changedColumns(rule: Rule, before: Rule | undefined): Set<string> {
  if (!before || before.kind !== rule.kind) return new Set(["*"]);
  const changed = new Set<string>();
  const differ = (col: string, a: unknown, b: unknown) => {
    if (a !== b) changed.add(col);
  };
  differ("target", nameOf(rule), nameOf(before));
  differ("source", sourceOf(rule), sourceOf(before));
  differ("expression", expressionOf(rule), expressionOf(before));
  differ("description", rule.description ?? "", before.description ?? "");
  if (rule.kind === "field" && before.kind === "field") {
    differ("type", rule.type, before.type);
    differ("req", rule.required, before.required);
    differ("validated", rule.validation.validated, before.validation.validated);
    differ("review", rule.validation.needs_review, before.validation.needs_review);
    differ("notes", rule.validation.notes ?? "", before.validation.notes ?? "");
  }
  return changed;
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

/** Every lookup rule of the file with its path (they can sit inside containers). */
export function lookups(rules: Rule[], prefix = "rules"): { path: string; rule: LookupRule }[] {
  const found: { path: string; rule: LookupRule }[] = [];
  rules.forEach((rule, i) => {
    const path = `${prefix}[${i}]`;
    if (rule.kind === "lookup") found.push({ path, rule });
    else if (rule.kind === "object" || rule.kind === "loop") {
      found.push(...lookups(rule.rules, `${path}.rules`));
    }
  });
  return found;
}

/** A lookup value as the table shows it: strings bare, everything else as JSON. */
export function showValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** Typed text back to a value of the declared type. Text that does not read as that type
 * stays a string, so the check reports it instead of the table silently changing it. */
export function parseTyped(text: string, type: string | null): unknown {
  if (type === null || type === "") return parseValue(text);
  const trimmed = text.trim();
  if (type === "int") return /^-?\d+$/.test(trimmed) ? Number(trimmed) : text;
  if (type === "number") return /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(trimmed) ? Number(trimmed) : text;
  if (type === "bool") return trimmed === "true" ? true : trimmed === "false" ? false : text;
  return text;
}

/** Typed text back to a value when no type is declared: a JSON number / true / false / null keeps that type,
 * anything else is a string. Quote it (`"1"`) to force a string that looks like one. */
export function parseValue(text: string): unknown {
  const trimmed = text.trim();
  if (/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(trimmed) || ["true", "false", "null"].includes(trimmed)) {
    return JSON.parse(trimmed) as unknown;
  }
  if (/^".*"$/.test(trimmed)) {
    try {
      return JSON.parse(trimmed) as unknown;
    } catch {
      return text;
    }
  }
  return text;
}

/** `entries` with `from` renamed to `to`, keeping its position; unchanged if `to` is taken. */
export function renameEntry(
  entries: Record<string, unknown>,
  from: string,
  to: string,
): Record<string, unknown> {
  if (from === to || to === "" || to in entries) return entries;
  return Object.fromEntries(Object.entries(entries).map(([k, v]) => [k === from ? to : k, v]));
}

/** `entries` plus a new row with a free key (`key`, `key2`, …). */
export function addEntry(entries: Record<string, unknown>): Record<string, unknown> {
  let key = "key";
  for (let n = 2; key in entries; n++) key = `key${n}`;
  return { ...entries, [key]: "" };
}
