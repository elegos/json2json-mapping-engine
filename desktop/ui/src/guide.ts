import { pagesFrom } from "./guideModel";

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
