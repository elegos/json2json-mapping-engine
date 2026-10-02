import type { GoldenResult } from "./api";

export type Verdict = "pass" | "fail" | "shown";

/** pass / fail, or "shown" when the case has no expected output to judge against. */
export function verdict(r: GoldenResult): Verdict {
  return r.passed === true ? "pass" : r.passed === false ? "fail" : "shown";
}

/** How many cases passed, failed or were only shown. */
export function tally(results: GoldenResult[]): Record<Verdict, number> {
  const count: Record<Verdict, number> = { pass: 0, fail: 0, shown: 0 };
  for (const r of results) count[verdict(r)]++;
  return count;
}

/** The line of a one-case summary: what failed, in words. */
export function whyFailed(r: GoldenResult): string[] {
  const reasons: string[] = [];
  if (r.diff) reasons.push("the output is not the expected one");
  const reported = r.errors.map((e) => e.rule).sort();
  if (r.expected_errors === null) {
    if (reported.length) reasons.push(`rules reported errors (${reported.join(", ")}) and none were expected`);
  } else if (JSON.stringify(reported) !== JSON.stringify([...r.expected_errors].sort())) {
    reasons.push(
      `rule errors were [${reported.join(", ")}], expected [${[...r.expected_errors].sort().join(", ")}]`,
    );
  }
  if (r.message && !reasons.length) reasons.push(r.message);
  return reasons;
}

/** A diff's lines with what each is: added, removed, or neither. */
export function diffLines(diff: string): { kind: "add" | "del" | "ctx"; text: string }[] {
  return diff
    .split("\n")
    .filter((l) => l !== "")
    .map((text) => ({
      kind: text.startsWith("+") && !text.startsWith("+++") ? "add" : text.startsWith("-") && !text.startsWith("---") ? "del" : "ctx",
      text,
    }));
}
