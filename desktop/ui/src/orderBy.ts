/** `order by`, as a loop's `order_by` and a selection's condition write it (transpiler/orderby.py):
 *  `<expression> [asc | desc] [nulls first | nulls last], ...`. */
export interface OrderKey {
  expr: string;
  desc: boolean;
  nullsFirst: boolean;
}

/** `text` cut at `sep` outside brackets and quotes. */
export function splitTopLevel(text: string, sep = ","): string[] {
  const parts: string[] = [];
  let depth = 0;
  let quote = "";
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) quote = "";
    } else if (ch === "'" || ch === '"') quote = ch;
    else if ("([{".includes(ch)) depth++;
    else if (")]}".includes(ch)) depth--;
    else if (ch === sep && depth === 0) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(text.slice(start));
  return parts;
}

const TAIL = /^([\s\S]*?)(?:\s+(asc|desc))?(?:\s+nulls\s+(first|last))?\s*$/i;

/** The keys of an order by list; an empty text has none. A part that cannot be read is kept whole,
 *  as an expression, for the file's own check to say what is wrong with it. */
export function parseOrderBy(text: string | null | undefined): OrderKey[] {
  if (!text || !text.trim()) return [];
  return splitTopLevel(text).map((part) => {
    const found = TAIL.exec(part.trim());
    return {
      expr: (found?.[1] ?? part).trim(),
      desc: (found?.[2] ?? "").toLowerCase() === "desc",
      nullsFirst: (found?.[3] ?? "").toLowerCase() === "first",
    };
  });
}

export function formatOrderBy(keys: OrderKey[]): string {
  return keys
    .filter((k) => k.expr.trim() !== "")
    .map((k) => `${k.expr.trim()}${k.desc ? " desc" : ""}${k.nullsFirst ? " nulls first" : ""}`)
    .join(", ");
}
