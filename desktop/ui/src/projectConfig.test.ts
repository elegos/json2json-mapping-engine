import { describe, expect, it } from "vitest";
import { type ConfigSchema, withTargetDefaults } from "./projectConfig";

const schema: ConfigSchema = {
  engine: [],
  targets: {
    plsql: [
      { key: "schema", kind: "string", help: "", required: true, default: null, choices: [] },
      { key: "functions_package", kind: "string", help: "", required: false, default: "F", choices: [] },
      { key: "mapping_packages", kind: "table", help: "", required: false, default: {}, choices: [] },
    ],
    other: [],
  },
};

describe("choosing the active backend", () => {
  it("gives a backend with no table one holding its defaults, leaving the others' tables alone", () => {
    const before = { project: { target: "plsql" }, target: { other: { x: 1 } } };
    expect(withTargetDefaults(before, schema)).toEqual({
      project: { target: "plsql" },
      target: { other: { x: 1 }, plsql: { functions_package: "F" } },
    });
  });

  it("keeps a table the file already has", () => {
    const before = { project: { target: "plsql" }, target: { plsql: { schema: "A" } } };
    expect(withTargetDefaults(before, schema)).toBe(before);
  });
});
