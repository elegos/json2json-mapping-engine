import { useState } from "react";
import { createPortal } from "react-dom";

/** The advanced options of a loop rule, as the file keeps them (`sort`, `index_start`, `when_empty`...). */
export interface LoopOptionValues {
  label: string | null;
  sort_key: string | null;
  sort_reverse: boolean;
  index_start: number;
  when_empty: "omit" | "list" | null;
  parallel: number | null;
}

interface Props {
  /** The loop's name in the grid, for the title. */
  name: string;
  values: LoopOptionValues;
  onApply: (values: LoopOptionValues) => void;
  onCancel: () => void;
}

const NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** What a loop has set apart from its Source, Filter and Output, in one place: an icon beside the
 * loop opens it, so that every option of the file can be expressed without leaving the tool. */
export function LoopOptions({ name, values, onApply, onCancel }: Props) {
  const [label, setLabel] = useState(values.label ?? "");
  const [sortKey, setSortKey] = useState(values.sort_key ?? "");
  const [reverse, setReverse] = useState(values.sort_reverse);
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
      sort_key: sortKey.trim() || null,
      sort_reverse: sortKey.trim() ? reverse : false,
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
          if (e.key === "Escape") onCancel();
          if (e.key === "Enter" && (e.target as HTMLElement).tagName !== "SELECT") apply();
        }}
      >
        <h3>Loop options — {name}</h3>
        <label className="prompt-field">
          <span>Name for the element (label)</span>
          <input value={label} spellCheck={false} autoFocus onChange={(e) => setLabel(e.target.value)} />
          <small>{labelProblem ?? "Lets a rule inside write @name.field instead of @2.field."}</small>
        </label>
        <label className="prompt-field">
          <span>Order the list by</span>
          <input
            value={sortKey}
            spellCheck={false}
            placeholder="@.field"
            onChange={(e) => setSortKey(e.target.value)}
          />
          <small>A field of the element, as @.field. Empty: the order of the source.</small>
        </label>
        <label className="modal-option">
          <input type="checkbox" checked={reverse} disabled={!sortKey.trim()} onChange={(e) => setReverse(e.target.checked)} />
          Descending
        </label>
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
  if (rule.sort_key) parts.push(`ordered by ${String(rule.sort_key)}${rule.sort_reverse ? " ↓" : ""}`);
  if (rule.index_start) parts.push(`@index from ${String(rule.index_start)}`);
  if (rule.when_empty === "omit") parts.push("left out when empty");
  if (rule.when_empty === "list") parts.push("empty list when empty");
  if (rule.parallel) parts.push(`parallel ${String(rule.parallel)}`);
  return parts.join(", ");
}
