import { useState } from "react";
import { createPortal } from "react-dom";
import { newFileProblem, validFunctionName } from "./fnEditor";

interface Props {
  /** The project's `.fn` files that can take a function (not the built-in overrides). */
  files: string[];
  /** The file offered first, when it is among `files`. */
  last: string;
  /** Names of the functions that exist (built-in or the project's). */
  taken: string[];
  onDone: (result: { name: string; file: string } | null) => void;
}

/** Asks for the name of a new function and the file it goes in: one of the project's files, or
 * a new one (the select's "New file…" turns it into a text box, and the button beside the box
 * gives the select back). */
export function NewFunctionDialog({ files, last, taken, onDone }: Props) {
  const [name, setName] = useState("");
  const [choice, setChoice] = useState(files.includes(last) ? last : (files[0] ?? ""));
  const [fresh, setFresh] = useState(files.length === 0);
  const [freshName, setFreshName] = useState("functions");
  const file = fresh ? freshName : choice;
  const problem =
    validFunctionName(name) ??
    (taken.includes(name) ? "a function with that name exists" : null) ??
    (fresh ? newFileProblem(file, files) : null);
  const submit = () => problem === null && onDone({ name, file });
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
        <h3>New function</h3>
        <label className="prompt-field">
          <span>Function name</span>
          <input autoFocus value={name} spellCheck={false} onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="prompt-field">
          <span>In file</span>
          <div className="file-choice">
            {fresh ? (
              <>
                <input
                  aria-label="New file name"
                  value={freshName}
                  autoFocus={files.length > 0}
                  spellCheck={false}
                  onChange={(e) => setFreshName(e.target.value)}
                />
                {files.length > 0 && (
                  <button onClick={() => setFresh(false)} title="Choose one of the project's files">
                    ▾
                  </button>
                )}
              </>
            ) : (
              <select
                aria-label="File"
                value={choice}
                onChange={(e) => (e.target.value === "" ? setFresh(true) : setChoice(e.target.value))}
              >
                {files.map((f) => (
                  <option key={f} value={f}>
                    fn/{f}.fn
                  </option>
                ))}
                <option value="">New file…</option>
              </select>
            )}
          </div>
          <small>{fresh ? `fn/${freshName}.fn, made for the function` : "an existing file of the project"}</small>
        </div>
        <div className="prompt-problem">{problem ?? ""}</div>
        <div className="modal-buttons">
          <button className="primary" disabled={problem !== null} onClick={submit}>
            Create
          </button>
          <button onClick={() => onDone(null)}>Cancel</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
