import { describe, expect, it } from "vitest";
import {
  type Plan,
  type PlanQuestion,
  type PlanRule,
  answersFrom,
  applyReport,
  locationText,
  needsAttention,
  questionOrder,
  ruleTree,
  visibleRules,
} from "./importModel";

const rule = (id: string, level: PlanRule["confidence"]["level"] = "high", more: Partial<PlanRule> = {}): PlanRule => ({
  id,
  evidence: { locations: [{ sheet: "S" }], text: id },
  target: { path: `$.${id}` },
  intent: "copy",
  interpretation: id,
  confidence: { level },
  review: { state: "pending" },
  proposal: { fn_rule: { id } },
  ...more,
});

const child = (id: string, parent: string, level: PlanRule["confidence"]["level"] = "high") =>
  rule(id, level, { proposal: { fn_rule: { id }, parent_rule: parent } });

describe("rule tree", () => {
  it("puts children after their container, whatever the order of the plan", () => {
    const nodes = ruleTree([child("a", "box"), rule("box"), rule("z")]);
    expect(nodes.map((n) => [n.rule.id, n.depth])).toEqual([
      ["box", 0],
      ["a", 1],
      ["z", 0],
    ]);
  });

  it("never loses a rule whose parent chain loops", () => {
    const nodes = ruleTree([child("a", "b"), child("b", "a")]);
    expect(nodes.map((n) => n.rule.id).sort()).toEqual(["a", "b"]);
  });

  it("keeps the container of a rule that needs a look", () => {
    const nodes = ruleTree([rule("box"), child("fine", "box"), child("doubt", "box", "guess"), rule("other")]);
    expect(visibleRules(nodes, true).map((n) => n.rule.id)).toEqual(["box", "doubt"]);
    expect(visibleRules(nodes, false)).toHaveLength(4);
  });
});

describe("attention", () => {
  it("is asked of a rule that is not high, flagged, or fails its check", () => {
    expect(needsAttention(rule("a"))).toBe(false);
    expect(needsAttention(rule("a", "medium"))).toBe(true);
    expect(needsAttention({ confidence: { level: "high", flags: ["ambiguous"] } })).toBe(true);
    expect(needsAttention({ confidence: { level: "high" }, proposal: { check: { ok: false } } })).toBe(true);
  });
});

describe("questions", () => {
  const q = (id: string, rules: number, status?: PlanQuestion["status"]): PlanQuestion => ({
    id,
    topic: "t",
    text: id,
    scope: "mapping",
    rule_ids: Array.from({ length: rules }, (_, i) => `r${i}`),
    status,
  });

  it("asks the one that touches most rules first, keeping the written order among equals", () => {
    expect(questionOrder([q("a", 1), q("b", 5), q("c", 1)]).map((x) => x.id)).toEqual(["b", "a", "c"]);
  });

  it("sends back typed answers and skips, and leaves the rest open", () => {
    const qs = [q("a", 1), q("b", 1), q("c", 1), q("d", 1, "answered")];
    expect(
      answersFrom(qs, {
        a: { answer: " yes ", skip: false },
        b: { answer: "", skip: true },
        c: { answer: "  ", skip: false },
        d: { answer: "x", skip: false },
      }),
    ).toEqual([{ id: "a", answer: "yes" }, { id: "b", skip: true }]);
  });
});

describe("apply report", () => {
  const plan = (rules: PlanRule[], more: Partial<Plan> = {}): Plan =>
    ({ rules, questions: [], discrepancies: [], schemas: {}, ...more }) as unknown as Plan;

  it("counts what goes in and tells what is left", () => {
    const rejected = rule("r");
    rejected.review.state = "rejected";
    const r = applyReport(
      plan([rule("a"), rule("b", "low"), rejected, rule("gap", "guess", { proposal: {} })], {
        lookups: [{ name: "UOM", status: "missing" }],
      }),
      true,
    );
    expect(r).toMatchObject({ included: 2, rejected: 1, pending: 2, gaps: 1, blockers: [] });
    expect(r.warnings.join("\n")).toMatch(/UOM/);
    expect(r.warnings.join("\n")).toMatch(/replaces/);
  });

  it("blocks a plan with nothing to write", () => {
    expect(applyReport(plan([]), false).blockers).toHaveLength(1);
  });
});

describe("locations", () => {
  it("reads like the document is addressed", () => {
    expect(locationText({ sheet: "Map", cells: "A4:E4" })).toBe("Map!A4:E4");
    expect(locationText({ table: "t2", row: 7 })).toBe("table t2, row 7");
    expect(locationText({})).toMatch(/somewhere/);
  });
});
