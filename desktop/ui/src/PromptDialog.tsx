import { useState } from "react";
import { createPortal } from "react-dom";

export interface PromptField {
  key: string;
  label: string;
  value: string;
  /** A line under the field. */
  hint?: string;
}

interface Props {
  title: string;
  fields: PromptField[];
  confirm: string;
  /** The reason the values cannot be used, or null. Shown under the fields; the button waits. */
  validate: (values: Record<string, string>) => string | null;
  onDone: (values: Record<string, string> | null) => void;
}

/** A modal asking for a few text values (Enter confirms, Escape or a click outside cancels). */
export function PromptDialog({ title, fields, confirm, validate, onDone }: Props) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.key, f.value])),
  );
  const problem = validate(values);
  const submit = () => problem === null && onDone(values);
  return createPortal(
    <div className="modal-backdrop" onClick={() => onDone(null)}>
      <div
        className="modal prompt"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onDone(null);
          if (e.key === "Enter") submit();
        }}
      >
        <h3>{title}</h3>
        {fields.map((f, i) => (
          <label key={f.key} className="prompt-field">
            <span>{f.label}</span>
            <input
              autoFocus={i === 0}
              value={values[f.key]}
              spellCheck={false}
              onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
            />
            {f.hint && <small>{f.hint}</small>}
          </label>
        ))}
        <div className="prompt-problem">{problem ?? ""}</div>
        <div className="modal-buttons">
          <button className="primary" disabled={problem !== null} onClick={submit}>
            {confirm}
          </button>
          <button onClick={() => onDone(null)}>Cancel</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
