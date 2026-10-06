import { useEffect, useRef, useState } from "react";
import type { GoldenCase } from "./api";
import { baseName, outputLight, type OutputSource } from "./ruleOutput";

interface Props {
  cases: GoldenCase[];
  source: OutputSource | null;
  /** The chosen file could not be read (moved, deleted). */
  fileMissing: boolean;
  /** The file remembered from the last time, offered again when another source is chosen. */
  rememberedFile: string | null;
  onPick: (source: OutputSource | null) => void;
  onChooseFile: () => void;
  /** Runs the mapping again on the input (the file may have changed, and so the mapping). */
  onRefresh: () => void;
}

/** Which input the grid's Output column is computed from: none, a golden case (compared with its
 * expected output) or any JSON file (just shown). The light is green when the input is there. */
export function OutputInputButton({ cases, source, fileMissing, rememberedFile, onPick, onChooseFile, onRefresh }: Props) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const light = outputLight(source, cases.map((c) => c.name), fileMissing);
  // the name of the file or case is in the tooltip: the label is the same whatever is chosen
  const label = "Example input file";
  const title = !source
    ? "Show what each rule gives on an input: a golden case or any JSON file"
    : source.kind === "case"
      ? light === "ok"
        ? `Golden case ${source.name}: the Output column compares with its expected output`
        : `The case ${source.name} is no longer there`
      : light === "ok"
        ? `${source.path}\nThe Output column shows what the rules give on this file`
        : `${source.path}\nThe file cannot be read`;
  const choose = (next: OutputSource | null) => {
    setOpen(false);
    onPick(next);
  };

  return (
    <div className="output-input" ref={box}>
      <div className="split">
        <button
          className={`schema-button split-main ${light}`}
          title={title}
          onClick={() => setOpen(!open)}
          aria-haspopup="menu"
        >
          <span className={`light ${light}`} />
          {label}
        </button>
        <button
          className="split-caret refresh"
          title="Run the mapping again on this input (the changes not saved are saved first)"
          aria-label="Run again"
          disabled={!source}
          onClick={onRefresh}
        >
          ↻
        </button>
      </div>
      {open && (
        <div className="output-menu" role="menu">
          <button role="menuitem" onClick={() => choose(null)}>
            No output
          </button>
          {cases.length > 0 && <div className="output-group">Golden cases</div>}
          {cases.map((c) => (
            <button
              key={c.name}
              role="menuitem"
              className={source?.kind === "case" && source.name === c.name ? "current" : ""}
              onClick={() => choose({ kind: "case", name: c.name })}
            >
              {c.name}
              {!c.expected && <span className="muted"> (no expected output)</span>}
            </button>
          ))}
          <div className="output-group">A file</div>
          {rememberedFile && !(source?.kind === "file" && source.path === rememberedFile) && (
            <button role="menuitem" title={rememberedFile} onClick={() => choose({ kind: "file", path: rememberedFile })}>
              {baseName(rememberedFile)}
            </button>
          )}
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onChooseFile();
            }}
          >
            Choose a JSON file…
          </button>
        </div>
      )}
    </div>
  );
}
