import { useState } from "react";
import { createPortal } from "react-dom";

export interface NewRuleValues {
  name?: string;
  type?: string;
  required?: boolean;
}

interface Props {
  /** `field`, `object` or `loop`. */
  kind: string;
  /** Adds the rule; the reason it was refused (shown in the dialog), or null once added. */
  onSubmit: (values: NewRuleValues) => Promise<string | null>;
  onCancel: () => void;
}

const TYPES = ["str", "int", "number", "bool", "date", "datetime"];
const NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;
const TITLES: Record<string, string> = { field: "New field", object: "New object", loop: "New loop" };

/** The modal behind "+ Add": the name of the new rule and, for a field, its type and Req. */
export function NewRuleDialog({ kind, onSubmit, onCancel }: Props) {
  const [name, setName] = useState("");
  const [type, setType] = useState("str");
  const [required, setRequired] = useState(true);
  const [refused, setRefused] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const trimmed = name.trim();
  const problem = trimmed === "" ? "" : NAME.test(trimmed) ? null : "Letters, digits and _, not starting with a digit.";
  const ready = trimmed !== "" && problem === null && !busy;
  const submit = async () => {
    if (!ready) return;
    setBusy(true);
    const error = await onSubmit({ name: trimmed, ...(kind === "field" ? { type, required } : {}) });
    setBusy(false);
    setRefused(error);
  };
  return createPortal(
    <div className="modal-backdrop" onClick={onCancel}>
      <div
        className="modal prompt"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onCancel();
          if (e.key === "Enter") void submit();
        }}
      >
        <h3>{TITLES[kind] ?? "New rule"}</h3>
        <label className="prompt-field">
          <span>{kind === "field" ? "Field name" : "Name"}</span>
          <input
            autoFocus
            value={name}
            spellCheck={false}
            onChange={(e) => {
              setName(e.target.value);
              setRefused(null);
            }}
          />
          {kind === "loop" && <small>The list is written as {trimmed || "Name"}[*]; set its Source after.</small>}
        </label>
        {kind === "field" && (
          <div className="new-rule-row">
            <label className="prompt-field">
              <span>Type</span>
              <select value={type} onChange={(e) => setType(e.target.value)}>
                {TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="new-rule-required">
              <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} /> Required
            </label>
          </div>
        )}
        <div className="prompt-problem">{refused ?? problem ?? ""}</div>
        <div className="modal-buttons">
          <button className="primary" disabled={!ready} onClick={() => void submit()}>
            Add
          </button>
          <button onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
