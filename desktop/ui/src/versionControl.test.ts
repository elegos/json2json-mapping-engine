import { describe, expect, it } from "vitest";
import type { VcsConflictFile } from "./api";
import { pending, show } from "./VersionControl";

const file = (name: string, kind: VcsConflictFile["kind"], paths: string[]): VcsConflictFile => ({
  file: name,
  kind,
  items: paths.map((path) => ({
    path,
    base: null,
    mine: "a",
    remote: "b",
    mine_missing: false,
    remote_missing: false,
  })),
});

describe("show", () => {
  it("writes a string as it is, anything else as JSON, a deleted side as such", () => {
    expect(show("From B.", false)).toBe("From B.");
    expect(show({ path: "$.id" }, false)).toBe('{\n  "path": "$.id"\n}');
    expect(show(27, false)).toBe("27");
    expect(show(null, true)).toBe("(deleted)");
  });
});

describe("pending", () => {
  const files = [
    file("orders.fn.yaml", "rules", ["rules[oid].description", "rules[cur].source"]),
    file("text.fn", "functions", ["functions[first_word]"]),
    file("notes.txt", "text", []),
    file("manifest.json", "generated", []),
  ];

  it("counts the items of mapping and function files that have no choice yet", () => {
    expect(pending(files, {})).toBe(3);
    expect(pending(files, { "orders.fn.yaml": { "rules[oid].description": "mine" } })).toBe(2);
    expect(
      pending(files, {
        "orders.fn.yaml": { "rules[oid].description": "mine", "rules[cur].source": "remote" },
        "text.fn": { "functions[first_word]": "mine" },
      }),
    ).toBe(0);
  });

  it("does not count text or generated files: they have nothing to choose", () => {
    expect(pending([files[2], files[3]], {})).toBe(0);
  });
});
