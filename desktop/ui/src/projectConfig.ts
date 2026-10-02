// `mapper.toml` as the project-properties form sees it. The form is drawn from descriptors
// the Python side provides (`mapper serve`, op `config_read`): the engine's sections, and
// for the target the options its backend declares. Nothing here knows a backend's keys.

export interface ConfigOption {
  key: string;
  kind: "string" | "int" | "bool" | "choice" | "table";
  help: string;
  required: boolean;
  default: unknown;
  choices: string[];
  /** What a new project proposes for a key with no default (the user may change it). */
  suggest?: unknown;
  /** Limits the backend declares; the check reports a value outside them. */
  minimum?: number | null;
  maximum?: number | null;
  min_length?: number | null;
  max_length?: number | null;
  pattern?: string | null;
  pattern_hint?: string;
}

export interface ConfigSection {
  path: string[];
  title: string;
  options: ConfigOption[];
}

export interface ConfigSchema {
  engine: ConfigSection[];
  /** Options of each backend that declares them, by target name. */
  targets: Record<string, ConfigOption[]>;
  /** What each backend's integration tests need, the keys of `[target.<name>.test]`. */
  target_tests?: Record<string, ConfigOption[]>;
}

export type ConfigValues = Record<string, unknown>;

export interface ConfigIssue {
  /** Dotted (`target.plsql.schema`); empty for the file as a whole. */
  path: string;
  message: string;
}

/** The table at `path` (missing ones read as empty). */
export function tableAt(values: ConfigValues, path: string[]): Record<string, unknown> {
  let node: unknown = values;
  for (const part of path) {
    node = typeof node === "object" && node !== null ? (node as ConfigValues)[part] : undefined;
  }
  return typeof node === "object" && node !== null && !Array.isArray(node)
    ? (node as Record<string, unknown>)
    : {};
}

/** A copy of `values` with `key` of the table at `path` set (`undefined` removes it),
 * creating the tables on the way. */
export function setAt(
  values: ConfigValues,
  path: string[],
  key: string,
  value: unknown,
): ConfigValues {
  const [head, ...rest] = path;
  if (head === undefined) {
    const next = { ...values };
    if (value === undefined) delete next[key];
    else next[key] = value;
    return next;
  }
  const child = tableAt(values, [head]);
  return { ...values, [head]: setAt(child, rest, key, value) };
}

/** The value the form shows: what the file has, else the option's default. */
export function shownValue(table: Record<string, unknown>, option: ConfigOption): unknown {
  return option.key in table ? table[option.key] : option.default;
}

/** The problems of one dotted path. */
export function issuesAt(issues: ConfigIssue[], path: string[], key: string): string[] {
  const dotted = [...path, key].join(".");
  return issues.filter((i) => i.path === dotted).map((i) => i.message);
}

/** After the active backend was chosen: a backend with no table of its own in the file gets one,
 * holding the defaults its options declare (the others' tables stay as they are, so going back to
 * a backend finds its settings). The required keys without a default are left for the form to
 * report. */
export function withTargetDefaults(values: ConfigValues, schema: ConfigSchema): ConfigValues {
  const target = tableAt(values, ["project"]).target;
  if (typeof target !== "string" || target in tableAt(values, ["target"])) return values;
  const section: Record<string, unknown> = {};
  for (const o of schema.targets[target] ?? []) {
    if (o.default !== null && o.default !== undefined && o.kind !== "table") section[o.key] = o.default;
  }
  return setAt(values, ["target"], target, section);
}
