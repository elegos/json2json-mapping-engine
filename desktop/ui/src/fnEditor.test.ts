import { describe, expect, it } from "vitest";
import { appendFunction, argsTemplate, functionNames, parseArgs, validFunctionName } from "./fnEditor";

const TEXT = `# fn/text.fn
def first_word(s: str) -> str | None:
    """D."""
    return s

def _helper(x):
    return x

def pad(s: str, n: int, fill: str = " ", *rest: str) -> str:
    return s
`;

describe("project function editor text", () => {
  it("lists the public functions of a file", () => {
    expect(functionNames(TEXT)).toEqual(["first_word", "pad"]);
  });

  it("appends a skeleton after what is there", () => {
    const text = appendFunction(TEXT, "shout");
    expect(text.startsWith(TEXT.trimEnd())).toBe(true);
    expect(functionNames(text)).toEqual(["first_word", "pad", "shout"]);
    expect(appendFunction("", "f")).toMatch(/^def f\(value: str\) -> str:/);
  });

  it("proposes one placeholder per required parameter, by type", () => {
    expect(argsTemplate(TEXT, "first_word")).toBe('[""]');
    expect(argsTemplate(TEXT, "pad")).toBe('["", 0]');
    expect(argsTemplate(TEXT, "ghost")).toBe("[]");
  });

  it("reads the arguments as a JSON array", () => {
    expect(parseArgs('["a", 1]')).toEqual({ args: ["a", 1] });
    expect(parseArgs("{}")).toHaveProperty("error");
    expect(parseArgs("[1,")).toHaveProperty("error");
  });

  it("checks a function name", () => {
    expect(validFunctionName("shout_2")).toBeNull();
    expect(validFunctionName("_x")).not.toBeNull();
    expect(validFunctionName("2x")).not.toBeNull();
  });
});
