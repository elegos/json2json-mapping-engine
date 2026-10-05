import { useState } from "react";
import { createPortal } from "react-dom";

export interface Choice {
  id: string;
  label: string;
  primary?: boolean;
}

interface Props {
  message: string;
  choices: Choice[];
  /** `checked` is the state of the option, when the question has one. */
  onChoose: (id: string, checked: boolean) => void;
  /** A checkbox under the message (unchecked at first), e.g. "Delete also the golden records". */
  option?: string;
}

/** A modal question; the last choice is what Escape and a click outside answer. */
export function Confirm({ message, choices, onChoose, option }: Props) {
  const [checked, setChecked] = useState(false);
  const dismiss = choices[choices.length - 1].id;
  return createPortal(
    <div className="modal-backdrop" onClick={() => onChoose(dismiss, false)}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && onChoose(dismiss, false)}
      >
        <p>{message}</p>
        {option && (
          <label className="modal-option">
            <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
            {option}
          </label>
        )}
        <div className="modal-buttons">
          {choices.map((c) => (
            <button
              key={c.id}
              autoFocus={c.primary}
              className={c.primary ? "primary" : undefined}
              onClick={() => onChoose(c.id, checked)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
