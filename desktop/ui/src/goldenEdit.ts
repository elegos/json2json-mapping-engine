// The files of a golden case as the case editor treats them: text that must be JSON and, for the
// expected errors, a list of rule ids.

export type Role = "input" | "expected" | "errors" | "rejected" | "warnings";

export const ROLES: { id: Role; label: string; empty: string; about: string }[] = [
  { id: "input", label: "Input", empty: "{}", about: "The JSON document the mapping reads." },
  { id: "expected", label: "Expected output", empty: "{}", about: "The JSON document the mapping must produce." },
  {
    id: "errors",
    label: "Expected errors",
    empty: "[]",
    about: 'The rules expected to report an error, as a list of rule ids: ["rules[0]"].',
  },
  {
    id: "rejected",
    label: "Expected rejected",
    empty: "[]",
    about: 'The codes of the checks that reject the case, which then has no output: ["REQ-16"].',
  },
  {
    id: "warnings",
    label: "Expected warnings",
    empty: "[]",
    about: 'The codes of the checks that warn: ["W-01"].',
  },
];

export type Files = Record<Role, string | null>;

/** Why `text` cannot be saved as the file of `role`, or null. */
export function jsonProblem(role: Role, text: string): string | null {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (e) {
    return `Not valid JSON: ${e instanceof Error ? e.message : e}`;
  }
  if (role !== "input" && role !== "expected" && !(Array.isArray(value) && value.every((v) => typeof v === "string"))) {
    return `Must be a list of ${role === "errors" ? "rule ids" : "check codes"} (texts).`;
  }
  return null;
}

/** `text` indented; throws when it is not JSON. */
export function formatJson(text: string): string {
  return JSON.stringify(JSON.parse(text), null, 2);
}

/** The roles whose draft differs from what is saved. */
export function changedRoles(saved: Files, draft: Files): Role[] {
  return ROLES.map((r) => r.id).filter((id) => saved[id] !== draft[id]);
}

/** The first problem among the drafts that are to be written, as `Role: reason`. */
export function firstProblem(saved: Files, draft: Files): { role: Role; message: string } | null {
  for (const role of changedRoles(saved, draft)) {
    const text = draft[role];
    if (text === null) {
      if (role === "input") return { role, message: "A case needs its input." };
      continue;
    }
    const message = jsonProblem(role, text);
    if (message) return { role, message };
  }
  return null;
}
