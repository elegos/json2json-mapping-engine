// The Target / Source / Expression cell being edited, if any, so that something outside the
// grid (the function explorer) can put text into it.
import type { EditorView } from "@codemirror/view";

interface Active {
  view: EditorView;
  column: string;
}

let active: Active | null = null;
const listeners = new Set<() => void>();

const notify = () => listeners.forEach((fn) => fn());

export function setActiveCellEditor(view: EditorView, column: string): () => void {
  const mine: Active = { view, column };
  active = mine;
  notify();
  return () => {
    if (active === mine) {
      active = null;
      notify();
    }
  };
}

export function subscribeCellEditor(fn: () => void): () => void {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}

/** The column being edited, when a call can go into it: Source or Expression, or `code`, the
 * override of a rule (the same functions, by the same names, in the developer dialect). */
export function insertableColumn(): string | null {
  return active && (["source", "expression", "code"].includes(active.column))
    ? active.column
    : null;
}

/** Puts `call` at the cursor (replacing the selection); `select` is the part of it left
 * selected, the first argument to overwrite. False when no cell can take it. */
export function insertIntoCellEditor(call: string, select?: string): boolean {
  if (!active || insertableColumn() === null) return false;
  const { view } = active;
  const from = view.state.selection.main.from;
  const to = view.state.selection.main.to;
  const at = select ? call.indexOf(select) : -1;
  view.dispatch({
    changes: { from, to, insert: call },
    selection:
      at >= 0
        ? { anchor: from + at, head: from + at + (select?.length ?? 0) }
        : { anchor: from + call.length },
    userEvent: "input.type",
  });
  view.focus();
  return true;
}
