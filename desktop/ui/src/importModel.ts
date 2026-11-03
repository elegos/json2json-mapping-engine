// The import plan (`import/<mapping>/ir.json`, skills/import-functional-spec/references/ir.schema.json)
// as the import screens read it, and what they derive from it. Only the parts the screens show.

export type Level = "high" | "medium" | "low" | "guess";
export type ReviewState = "pending" | "accepted" | "edited" | "rejected" | "applied";

export interface Location {
  sheet?: string;
  cells?: string;
  page?: number;
  section?: string;
  paragraph?: number;
  line?: number;
  table?: string;
  row?: number;
}

export interface Evidence {
  locations: Location[];
  text: string;
  inherited_context?: { kind: string; text: string; location?: Location }[];
  condition_scope?: string;
  review_thread?: { author?: string; date?: string; text: string; kind?: string }[];
  markers?: { marker: string; meaning?: string; meaning_origin?: string }[];
}

export interface Confidence {
  level: Level;
  reasons?: string[];
  flags?: string[];
}

export interface PathRef {
  path: string;
  as_written?: string;
  in_schema?: boolean | null;
  closest_in_schema?: string;
}

export interface PlanCheck {
  ran?: boolean;
  ok?: boolean;
  errors?: string[];
  retries?: number;
}

export interface PlanRule {
  id: string;
  evidence: Evidence;
  target: PathRef;
  sources?: PathRef[];
  intent: string;
  interpretation: string;
  assumptions?: { topic: string; assumed: string; basis: string; question_id?: string }[];
  proposal?: {
    fn_rule?: Record<string, unknown>;
    parent_rule?: string;
    functions_used?: string[];
    functions_missing?: { needed: string; suggestion?: string }[];
    check?: PlanCheck;
  };
  confidence: Confidence;
  back_translation?: string;
  review: { state: ReviewState; note?: string; edited_by_user?: boolean };
}

export interface PlanValidation {
  id: string;
  side: "input" | "output";
  expect: string;
  code: string;
  message?: string;
  action: "reject" | "warn";
  evidence: Evidence;
  interpretation: string;
  confidence?: Confidence;
  review: { state?: string };
  check?: Record<string, unknown>;
}

export interface PlanQuestion {
  id: string;
  topic: string;
  text: string;
  scope: "profile" | "mapping" | "rule";
  proposal?: string;
  evidence?: { text: string; location?: Location }[];
  options?: string[];
  rule_ids?: string[];
  answer?: string;
  answered_at?: string;
  status?: "open" | "answered" | "skipped_assumed_proposal";
}

export interface Discrepancy {
  kind: string;
  severity: "error" | "warning" | "info";
  detail: string;
  rule_ids?: string[];
  paths?: string[];
  locations?: Location[];
}

export interface PlanTest {
  id: string;
  origin: Location;
  trust: "paired_in_document" | "inferred_pairing" | "single_value";
  input?: unknown;
  expected?: unknown;
  rule_ids?: string[];
  result?: "not_run" | "pass" | "fail" | "error";
  detail?: string;
  partial?: boolean;
  expected_rejected?: string[];
  expected_warnings?: string[];
}

export interface PlanLookup {
  name: string;
  status: "in_document" | "provided" | "partial" | "missing";
  entries?: Record<string, unknown>;
  not_found?: unknown;
  location?: Location;
}

export interface Coverage {
  units_total?: number;
  imported?: number;
  imported_with_doubt?: number;
  not_imported?: { location: Location; reason: string; detail?: string }[];
}

export interface Plan {
  ir_version: 1;
  mapping: { id: string; name?: string };
  document: {
    file: string;
    sha256: string;
    format?: string;
    version: { resolved: string; origin: string; candidates?: { origin: string; value: string }[] };
    mappings_found?: { id: string; rules?: number; imported?: boolean }[];
  };
  profile?: { name: string; sha256: string; origin?: string };
  schemas: Record<"input" | "output", { origin: string; path?: string; confirmed?: boolean }>;
  lookups?: PlanLookup[];
  validations?: PlanValidation[];
  schema_validation?: { input?: boolean; output?: boolean };
  rules: PlanRule[];
  questions: PlanQuestion[];
  discrepancies: Discrepancy[];
  coverage?: Coverage;
  tests?: PlanTest[];
}

export type ImportState = "needs_answers" | "answered" | "ready_for_review" | "applied" | "broken";

export interface ImportSummary {
  mapping: string;
  state: ImportState;
  error?: string;
  document?: string;
  version?: string;
  profile?: string;
  rules?: number;
  guesses?: number;
  open_questions?: number;
  stale?: string[];
  /** Units of the document still wait for a rule (batches left, or not translated yet). */
  unfinished?: boolean;
  modified?: string;
}

export interface ProfileInfo {
  name: string;
  description?: string | null;
  applies_to?: string[];
}

export interface PlanView {
  plan: Plan;
  state: ImportState;
  problems: string[];
  stale: string[];
  profile: { name: string; text: string } | null;
  exists: boolean;
}

export type Mode = "import" | "resume" | "rerun_all" | "rerun_partial" | "revalue_version";

/** What each state of an import offers to do next. */
export const NEXT_STEP: Record<ImportState, "questions" | "run" | "review" | "done" | "broken"> = {
  needs_answers: "questions",
  answered: "run",
  ready_for_review: "review",
  applied: "done",
  broken: "broken",
};

export const LEVEL_LABEL: Record<Level, string> = {
  high: "high",
  medium: "medium",
  low: "low",
  guess: "guess",
};

export const FLAG_LABEL: Record<string, string> = {
  ambiguous: "ambiguous",
  open_question_in_document: "question open in the document",
  unanswered_user_question: "unanswered question",
  contradiction: "contradiction",
  missing_lookup: "missing lookup",
  unknown_field: "unknown field",
  function_gap: "function gap",
  schema_mismatch: "schema mismatch",
  no_schema: "no schema",
  removed_in_document: "removed in the document",
  conflicting_markers: "conflicting markers",
  unconfirmed_convention: "unconfirmed convention",
  multi_reading: "several readings",
  unparsed_expression: "expression not parsed",
};

/** A rule or check that deserves a look: not `high`, flagged, failing its check, or noted. */
export function needsAttention(item: { confidence?: Confidence; proposal?: PlanRule["proposal"] }): boolean {
  const level = item.confidence?.level ?? "high";
  return (
    level !== "high" ||
    (item.confidence?.flags?.length ?? 0) > 0 ||
    item.proposal?.check?.ok === false ||
    (item.proposal?.functions_missing?.length ?? 0) > 0
  );
}

export interface RuleNode {
  rule: PlanRule;
  depth: number;
}

/** The rules in the document's order, each with how deep it sits (its `parent_rule` chain): a
 * container is followed by its children. The parent is the fn rule's id, which the plan rule
 * of that container carries in `proposal.fn_rule.id`. */
export function ruleTree(rules: readonly PlanRule[]): RuleNode[] {
  const byFn = new Map<string, PlanRule>();
  for (const r of rules) {
    const id = r.proposal?.fn_rule?.id;
    if (typeof id === "string") byFn.set(id, r);
  }
  const children = new Map<string, PlanRule[]>();
  const top: PlanRule[] = [];
  for (const r of rules) {
    const parent = r.proposal?.parent_rule;
    const holder = parent ? byFn.get(parent) : undefined;
    if (holder && holder !== r) {
      const list = children.get(holder.id) ?? [];
      list.push(r);
      children.set(holder.id, list);
    } else {
      top.push(r);
    }
  }
  const out: RuleNode[] = [];
  const seen = new Set<string>();
  const walk = (r: PlanRule, depth: number) => {
    if (seen.has(r.id)) return;
    seen.add(r.id);
    out.push({ rule: r, depth });
    for (const c of children.get(r.id) ?? []) walk(c, depth + 1);
  };
  for (const r of top) walk(r, 0);
  for (const r of rules) walk(r, 0); // a parent chain that loops: shown flat, never lost
  return out;
}

/** The nodes to list: with the filter on, the ones that need attention and the containers they sit in. */
export function visibleRules(nodes: readonly RuleNode[], onlyAttention: boolean): RuleNode[] {
  if (!onlyAttention) return [...nodes];
  const keep = new Set<number>();
  nodes.forEach((n, i) => {
    if (!needsAttention(n.rule)) return;
    keep.add(i);
    let depth = n.depth;
    for (let j = i - 1; j >= 0 && depth > 0; j--) {
      if (nodes[j].depth < depth) {
        keep.add(j);
        depth = nodes[j].depth;
      }
    }
  });
  return nodes.filter((_, i) => keep.has(i));
}

export function countByLevel(items: readonly { confidence?: Confidence }[]): Record<Level, number> {
  const out: Record<Level, number> = { high: 0, medium: 0, low: 0, guess: 0 };
  for (const i of items) out[i.confidence?.level ?? "high"]++;
  return out;
}

/** Open questions first by the number of rules each one touches (the most consequential), then in
 * the order the skill wrote them. */
export function questionOrder(questions: readonly PlanQuestion[]): PlanQuestion[] {
  return questions
    .map((q, i) => ({ q, i }))
    .sort((a, b) => (b.q.rule_ids?.length ?? 0) - (a.q.rule_ids?.length ?? 0) || a.i - b.i)
    .map(({ q }) => q);
}

export const isOpen = (q: PlanQuestion) => (q.status ?? "open") === "open";

/** Notes the user left on rules are answered questions of topic `user_note`: not asked again. */
export const isNote = (q: PlanQuestion) => q.topic === "user_note";

export interface Draft {
  /** The text typed or the option picked. */
  answer: string;
  skip: boolean;
}

/** What goes back to the plan for a draft set: an answer (typed or the proposal as it is), or the
 * proposal taken on trust (`skip`). A question with neither is left open. */
export function answersFrom(
  questions: readonly PlanQuestion[],
  drafts: Readonly<Record<string, Draft | undefined>>,
): { id: string; answer?: string; skip?: boolean }[] {
  const out: { id: string; answer?: string; skip?: boolean }[] = [];
  for (const q of questions) {
    const d = drafts[q.id];
    if (!d || !isOpen(q)) continue;
    if (d.skip) out.push({ id: q.id, skip: true });
    else if (d.answer.trim() !== "") out.push({ id: q.id, answer: d.answer.trim() });
  }
  return out;
}

export function ruleCountOf(question: PlanQuestion): number {
  return question.rule_ids?.length ?? 0;
}

export function locationText(l: Location): string {
  const parts: string[] = [];
  if (l.sheet) parts.push(l.cells ? `${l.sheet}!${l.cells}` : l.sheet);
  else if (l.cells) parts.push(l.cells);
  if (l.table) parts.push(l.row === undefined ? `table ${l.table}` : `table ${l.table}, row ${l.row}`);
  if (l.page) parts.push(`page ${l.page}`);
  if (l.section) parts.push(`§ ${l.section}`);
  if (l.paragraph !== undefined) parts.push(`paragraph ${l.paragraph}`);
  if (l.line !== undefined) parts.push(`line ${l.line}`);
  return parts.join(", ") || "(somewhere in the document)";
}

export interface ApplyReport {
  included: number;
  rejected: number;
  pending: number;
  gaps: number;
  failing: PlanRule[];
  blockers: string[];
  warnings: string[];
}

/** What applying the plan would do, from the plan alone: the working copy is built from the rules
 * that are not rejected and have a proposal; the rest is told, not hidden. */
export function applyReport(plan: Plan, exists: boolean): ApplyReport {
  const proposed = plan.rules.filter((r) => r.proposal?.fn_rule);
  const rejected = plan.rules.filter((r) => r.review.state === "rejected");
  const included = proposed.filter((r) => r.review.state !== "rejected");
  const failing = included.filter((r) => r.proposal?.check?.ok === false);
  const pending = included.filter((r) => r.review.state === "pending");
  const blockers: string[] = [];
  const warnings: string[] = [];
  if (included.length === 0) blockers.push("No rule would be written.");
  const open = plan.questions.filter((q) => isOpen(q));
  if (open.length) warnings.push(`${open.length} question(s) are still open: their rules use the proposal.`);
  if (failing.length) warnings.push(`${failing.length} rule(s) did not pass the check and are written flagged for review.`);
  const missing = plan.rules.filter((r) => !r.proposal?.fn_rule && r.review.state !== "rejected" && r.intent !== "not_mapped");
  if (missing.length) warnings.push(`${missing.length} rule(s) have no proposal (a missing function or an open question).`);
  const lookups = (plan.lookups ?? []).filter((l) => l.status === "missing" || l.status === "partial");
  if (lookups.length) warnings.push(`Lookup table(s) to fill in: ${lookups.map((l) => l.name).join(", ")}.`);
  const errors = plan.discrepancies.filter((d) => d.severity === "error");
  if (errors.length) warnings.push(`${errors.length} discrepancy(ies) of severity error.`);
  if (exists) warnings.push("A mapping with this name exists: applying replaces it.");
  return {
    included: included.length,
    rejected: rejected.length,
    pending: pending.length,
    gaps: missing.length,
    failing,
    blockers,
    warnings,
  };
}

export const MODE_LABEL: Record<Mode, string> = {
  import: "Import",
  resume: "Continue with the answers",
  rerun_all: "Redo every rule",
  rerun_partial: "Redo the rules with a note",
  revalue_version: "Read the new version of the document",
};

/** How the batches of a long import stand. */
export interface BatchCounts {
  total: number;
  done: number;
  running: number;
  pending: number;
  failed: number;
}

/** What the run screen shows while the assistants work (`import_live`). */
export interface LiveView {
  questions: PlanQuestion[];
  answered: number;
  rules: number;
  guesses: number;
  units: { units_total?: number; imported?: number; imported_with_doubt?: number };
  batches: BatchCounts | null;
  rule_labels: Record<string, string>;
}
