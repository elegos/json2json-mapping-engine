import { describe, expect, it } from "vitest";
import { pagesFrom, parseFigure, renderPage, searchPages, snippet } from "./guideModel";

const pages = pagesFrom({
  "./developer/02-b.md": "# Overrides\nPython subset in code_override.",
  "./functional/01-a.md": "# Target\nA name like `Lines[*]`.",
  "./functional/10-c.md": "# Source\nThe `$` root.",
  "./readme.md": "# Not a page",
});

describe("pages", () => {
  it("keeps the order of the books and files, and takes the title from the first heading", () => {
    expect(pages.map((p) => [p.id, p.title])).toEqual([
      ["developer/b", "Overrides"],
      ["functional/a", "Target"],
      ["functional/c", "Source"],
    ]);
  });

  it("searches titles and text, title matches first", () => {
    expect(searchPages(pages, "target").map((p) => p.id)).toEqual(["functional/a"]);
    expect(searchPages(pages, "python subset").map((p) => p.id)).toEqual(["developer/b"]);
    expect(searchPages(pages, "nothing here")).toEqual([]);
    expect(snippet(pages[0], "python")).toContain("Python subset");
  });
});

describe("figures", () => {
  const block = (extra = "") =>
    "```figure\n" +
    JSON.stringify({
      src: "grid.png",
      alt: "The grid",
      callouts: [
        { n: 1, x: 10, y: 20, w: 30, h: 5, text: "Target column" },
        { n: 2, x: 50, y: 20, w: 20, h: 5, text: "Source <column>", at: { x: 60, y: 60 } },
      ],
      ...JSON.parse(extra || "{}"),
    }) +
    "\n```";

  it("draws boxes, numbers, an arrow where asked and the legend", () => {
    const html = renderPage(block(), (s) => `/img/${s}`);
    expect(html).toContain('<img src="/img/grid.png"');
    expect(html.match(/callout-box/g)).toHaveLength(2);
    expect(html.match(/<line /g)).toHaveLength(1);
    expect(html).toContain("Source &lt;column&gt;");
  });

  it("shows a placeholder while the screenshot is missing, callouts kept", () => {
    const html = renderPage(block(), () => undefined);
    expect(html).toContain("Screenshot pending: The grid");
    expect(html).toContain("callout-badge");
  });

  it("reports a figure it cannot read instead of dropping it", () => {
    expect(parseFigure("{")).toMatch(/^figure:/);
    expect(renderPage("```figure\n{}\n```", () => undefined)).toContain("figure-error");
  });
});
