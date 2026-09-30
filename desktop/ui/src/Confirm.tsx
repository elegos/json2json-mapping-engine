export interface Choice {
  id: string;
  label: string;
  primary?: boolean;
}

interface Props {
  message: string;
  choices: Choice[];
  onChoose: (id: string) => void;
}

/** A modal question; the last choice is what Escape and a click outside answer. */
export function Confirm({ message, choices, onChoose }: Props) {
  const dismiss = choices[choices.length - 1].id;
  return (
    <div className="modal-backdrop" onClick={() => onChoose(dismiss)}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && onChoose(dismiss)}
      >
        <p>{message}</p>
        <div className="modal-buttons">
          {choices.map((c) => (
            <button
              key={c.id}
              autoFocus={c.primary}
              className={c.primary ? "primary" : undefined}
              onClick={() => onChoose(c.id)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
