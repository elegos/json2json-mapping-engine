import { useState } from "react";
import { chooseJsonFile } from "./api";

interface Props {
  mapping: string;
  /** Case names already in use. */
  taken: readonly string[];
  /** Resolves to a problem to show, or null when the case was loaded (the dialog closes). */
  onImport: (values: { name: string; input: string; expected: string | null; errors: string | null }) => Promise<string | null>;
  onClose: () => void;
}

const CASE_NAME = /^[A-Za-z0-9_][A-Za-z0-9_-]*$/;

/** A case name proposed from the input file's name: `my data.input.json` -> `my_data`. */
export function proposeName(file: string): string {
  const base = file.replace(/^.*[\\/]/, "").replace(/\.json$/i, "").replace(/\.input$/i, "");
  return base.replace(/[^A-Za-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "");
}

const short = (path: string) => path.replace(/^.*[\\/]/, "");

/** Loading a golden case: one file for each role (the tool copies them in under the standard
 * names, so a file's role is decided here, not by what it was called). */
export function GoldenImport({ mapping, taken, onImport, onClose }: Props) {
  const [input, setInput] = useState<string | null>(null);
  const [expected, setExpected] = useState<string | null>(null);
  const [errors, setErrors] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [edited, setEdited] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const problem = !input
    ? "Choose the input file."
    : !CASE_NAME.test(name)
      ? "The case name: letters, digits, _ and -."
      : taken.includes(name)
        ? `There is already a case called ${name}.`
        : null;

  const pick = async (title: string, set: (path: string | null) => void, isInput = false) => {
    const file = await chooseJsonFile(title);
    if (!file) return;
    set(file);
    if (isInput && !edited) setName(proposeName(file));
  };

  const row = (label: string, value: string | null, set: (path: string | null) => void, title: string, optional: boolean, isInput = false) => (
    <div className="golden-row">
      <span className="golden-role">{label}</span>
      <span className="golden-file" title={value ?? ""}>
        {value ? short(value) : <span className="golden-none">{optional ? "none" : "not chosen"}</span>}
      </span>
      <button onClick={() => void pick(title, set, isInput)}>{value ? "Change…" : "Choose…"}</button>
      {optional && value && <button title="Remove" onClick={() => set(null)}>✕</button>}
    </div>
  );

  const submit = async () => {
    if (problem !== null || !input) return;
    setBusy(true);
    setFailure(await onImport({ name, input, expected, errors }));
    setBusy(false);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal prompt golden-import"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
      >
        <h3>Import a golden case</h3>
        {row("Input", input, setInput, "Input JSON of the case", false, true)}
        {row("Expected output", expected, setExpected, "Expected output JSON", true)}
        {row("Expected errors", errors, setErrors, "Expected rule errors (a JSON list of rule ids)", true)}
        <label className="prompt-field">
          <span>Case name</span>
          <input
            value={name}
            spellCheck={false}
            onChange={(e) => {
              setName(e.target.value.trim());
              setEdited(true);
            }}
          />
          <small>
            Saved as tests/golden/{mapping}/{name || "<case>"}.input.json (and .expected.json,
            .expected_errors.json).
          </small>
        </label>
        <div className="prompt-problem">{failure ?? problem ?? ""}</div>
        <div className="modal-buttons">
          <button className="primary" disabled={problem !== null || busy} onClick={() => void submit()}>
            Import
          </button>
          <button onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
