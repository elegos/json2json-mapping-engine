import { useState } from "react";
import { createPortal } from "react-dom";
import { CodeEditor, type Completer } from "./CodeEditor";
import { type OrderKey, formatOrderBy, parseOrderBy } from "./orderBy";

/** The advanced options of a loop rule, as the file keeps them (`sort`, `index_start`, `when_empty`...). */
export interface LoopOptionValues {
  label: string | null;
  /** `<expression> [asc|desc] [nulls first|last], ...` */
  order_by: string | null;
  index_start: number;
  when_empty: "omit" | "list" | null;
  parallel: number | null;
}

interface Props {
  /** The loop's name in the grid, for the title. */
  name: string;
  values: LoopOptionValues;
  /** Suggestions for a key's expression (the loop's element is `@`). */
  complete?: Completer;
  onApply: (values: LoopOptionValues) => void;
  onCancel: () => void;
}

const NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** What a loop has set apart from its Source, Filter and Output, in one place: an icon beside the
 * loop opens it, so that every option of the file can be expressed without leaving the tool. */
export function LoopOptions({ name, values, complete, onApply, onCancel }: Props) {
  const [label, setLabel] = useState(values.label ?? "");
  const [keys, setKeys] = useState<OrderKey[]>(parseOrderBy(values.order_by));
  const [start, setStart] = useState(String(values.index_start));
  const [empty, setEmpty] = useState<string>(values.when_empty ?? "");
  const [parallel, setParallel] = useState(values.parallel === null ? "" : String(values.parallel));
  const labelProblem = label.trim() !== "" && !NAME.test(label.trim()) ? "Letters, digits and _, not starting with a digit." : null;
  const startProblem = !/^-?\d+$/.test(start.trim()) ? "A whole number." : null;
  const parallelProblem = parallel.trim() !== "" && !/^\d+$/.test(parallel.trim()) ? "A whole number, or empty." : null;
  const ready = !labelProblem && !startProblem && !parallelProblem;
  const apply = () => {
    if (!ready) return;
    onApply({
      label: label.trim() || null,
      order_by: formatOrderBy(keys) || null,
      index_start: Number(start.trim()),
      when_empty: empty === "omit" || empty === "list" ? empty : null,
      parallel: parallel.trim() ? Number(parallel.trim()) : null,
    });
  };
  return createPortal(
    <div className="modal-backdrop" onClick={onCancel}>
      <div
        className="modal loop-options"
        role="dialog"
        aria-modal="true"
        aria-label="Loop options"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          // an editor that used the key (it closed its suggestions) has prevented the default
          if (e.key === "Escape" && !e.defaultPrevented) onCancel();
          if (e.key === "Enter" && (e.target as HTMLElement).tagName !== "SELECT" && !(e.target as HTMLElement).closest(".cm-editor")) apply();
        }}
      >
        <h3>Loop options — {name}</h3>
        <label className="prompt-field">
          <span>Name for the element (label)</span>
          <input value={label} spellCheck={false} autoFocus onChange={(e) => setLabel(e.target.value)} />
          <small>{labelProblem ?? "Lets a rule inside write @name.field instead of @2.field."}</small>
        </label>
        <fieldset className="order-keys">
          <legend>Order the list by</legend>
          {keys.map((key, n) => (
            <div className="order-key" key={n}>
              <CodeEditor
                className="order-expr"
                value={key.expr}
                completer={complete}
                onCancel={onCancel}
                onChange={(text) => setKeys(keys.map((k, i) => (i === n ? { ...k, expr: text } : k)))}
              />
              <select
                aria-label={`Direction of key ${n + 1}`}
                value={key.desc ? "desc" : "asc"}
                onChange={(e) => setKeys(keys.map((k, i) => (i === n ? { ...k, desc: e.target.value === "desc" } : k)))}
              >
                <option value="asc">ascending</option>
                <option value="desc">descending</option>
              </select>
              <select
                aria-label={`Empty values of key ${n + 1}`}
                value={key.nullsFirst ? "first" : "last"}
                onChange={(e) => setKeys(keys.map((k, i) => (i === n ? { ...k, nullsFirst: e.target.value === "first" } : k)))}
              >
                <option value="last">empty last</option>
                <option value="first">empty first</option>
              </select>
              <button className="link" title="Remove this key" onClick={() => setKeys(keys.filter((_, i) => i !== n))}>
                ✕
              </button>
            </div>
          ))}
          <button className="link" onClick={() => setKeys([...keys, { expr: "", desc: false, nullsFirst: false }])}>
            + Add a key
          </button>
          <small>
            Each key is an expression of the element; the next one breaks the ties of the one before. No key: the order of
            the source.
          </small>
        </fieldset>
        <label className="prompt-field">
          <span>First number (@index)</span>
          <input value={start} inputMode="numeric" onChange={(e) => setStart(e.target.value)} />
          <small>{startProblem ?? "0 numbers the elements from 0, 1 from 1."}</small>
        </label>
        <label className="prompt-field">
          <span>When there is nothing to list</span>
          <select value={empty} onChange={(e) => setEmpty(e.target.value)}>
            <option value="">Default: left out, unless the output schema requires the list</option>
            <option value="omit">Leave the list out</option>
            <option value="list">Write an empty list</option>
          </select>
        </label>
        <label className="prompt-field">
          <span>Parallel degree</span>
          <input value={parallel} inputMode="numeric" placeholder="none" onChange={(e) => setParallel(e.target.value)} />
          <small>{parallelProblem ?? "How many workers may map the elements at once (Python and PL/SQL targets that support it)."}</small>
        </label>
        <div className="modal-buttons">
          <button onClick={onCancel}>Cancel</button>
          <button className="primary" disabled={!ready} onClick={apply}>
            Apply
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** What a loop has set, in a few words for the grid (empty: nothing). */
export function loopOptionsSummary(rule: Record<string, unknown>): string {
  const parts: string[] = [];
  if (rule.order_by) parts.push(`ordered by ${String(rule.order_by)}`);
  if (rule.index_start) parts.push(`@index from ${String(rule.index_start)}`);
  if (rule.when_empty === "omit") parts.push("left out when empty");
  if (rule.when_empty === "list") parts.push("empty list when empty");
  if (rule.parallel) parts.push(`parallel ${String(rule.parallel)}`);
  return parts.join(", ");
}
