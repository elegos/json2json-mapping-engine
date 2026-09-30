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
}

export function flatten(rules: Rule[], prefix = "rules", depth = 0): Row[] {
  const rows: Row[] = [];
  rules.forEach((rule, i) => {
    const path = `${prefix}[${i}]`;
    rows.push({ path, depth, rule });
    if (rule.kind === "object" || rule.kind === "loop") {
      rows.push(...flatten(rule.rules, `${path}.rules`, depth + 1));
    }
  });
  return rows;
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

/** What the "Name" column shows and edits, per kind. */
export function nameOf(rule: Rule): string {
  switch (rule.kind) {
    case "field":
      return rule.field;
    case "lookup":
      return rule.label;
    default:
      return rule.output;
  }
}

export function setName(rule: Rule, value: string): void {
  if (rule.kind === "field") rule.field = value;
  else if (rule.kind === "lookup") rule.label = value;
  else rule.output = value;
}

/** Source column: a field's `source.path`, a loop's `source`. */
export function sourceOf(rule: Rule): string {
  if (rule.kind === "field") return rule.source_path ?? "";
  if (rule.kind === "loop") return rule.source;
  return "";
}

export function setSource(rule: Rule, value: string): void {
  if (rule.kind === "field") rule.source_path = value || null;
  else if (rule.kind === "loop") rule.source = value;
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
  message: string;
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
