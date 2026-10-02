import { type Callout, pagesFrom } from "./guideModel";

const files = import.meta.glob("./guide/**/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const images = import.meta.glob("./guide/img/*", {
  query: "?url",
  import: "default",
  eager: true,
}) as Record<string, string>;

export const PAGES = pagesFrom(
  Object.fromEntries(Object.entries(files).map(([path, text]) => [path.replace("./guide", "."), text])),
);

/** URL of a figure's image (`grid.png`), or undefined while the screenshot is not there. */
export const imageUrl = (name: string): string | undefined => images[`./guide/img/${name}`];

const found = import.meta.glob("./guide/img/*.callouts.json", {
  import: "default",
  eager: true,
}) as Record<string, Callout[]>;

/** The callouts found when the screenshot `name` was taken (shots/run.mjs), if any. */
export const foundCallouts = (name: string): Callout[] | undefined =>
  found[`./guide/img/${name.replace(/\.[^.]+$/, "")}.callouts.json`];
