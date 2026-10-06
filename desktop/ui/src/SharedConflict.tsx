import { useState } from "react";
import { createPortal } from "react-dom";
import type { VcsConflictItem } from "./api";
import { show } from "./VersionControl";

type Side = "mine" | "remote";

interface Props {
  /** What is being merged, as the user knows it (a file name). */
  file: string;
  /** Who the other side is: "the shared folder" (a save), or "the copy" (a conflict copy). */
  other: string;
  kind: "rules" | "functions" | "text";
  items: VcsConflictItem[];
  onSettle: (choices: Record<string, Side>) => void;
  /** `mine` / `theirs`: for a file the tool cannot merge, which whole version to keep. */
  onWhole: (keep: Side) => void;
  onCancel: () => void;
}

/** Shared-folder mode: what two people changed in the same place, one choice per item, like the
 * git panel's (docs/ARCHITECTURE.md, §Shared-folder mode). */
export function SharedConflict({ file, other, kind, items, onSettle, onWhole, onCancel }: Props) {
  const [chosen, setChosen] = useState<Record<string, Side>>({});
  const left = items.filter((i) => !chosen[i.path]).length;
  return createPortal(
    <div className="modal-backdrop">
      <div className="modal vcs">
        <h3>{file}</h3>
        {kind === "text" ? (
          <>
            <p>
              The file was changed in {other} and cannot be merged by rule. Keep one whole version:
              the other is lost.
            </p>
            <div className="modal-buttons">
              <button onClick={onCancel}>Cancel</button>
              <button onClick={() => onWhole("remote")}>Keep the one in {other}</button>
              <button className="primary" onClick={() => onWhole("mine")}>
                Keep mine
              </button>
            </div>
          </>
        ) : (
          <>
            <p>
              You and someone else changed the same {kind === "rules" ? "rule fields" : "functions"}.
              Choose for each; everything else is merged.
            </p>
            {items.map((i) => (
              <div key={i.path} className="vcs-item">
                <code>{i.path}</code>
                <div className="vcs-sides">
                  {(["mine", "remote"] as const).map((side) => (
                    <label key={side} className={chosen[i.path] === side ? "on" : ""}>
                      <input
                        type="radio"
                        name={i.path}
                        checked={chosen[i.path] === side}
                        onChange={() => setChosen((old) => ({ ...old, [i.path]: side }))}
                      />
                      <b>{side === "mine" ? "Mine" : `In ${other}`}</b>
                      <pre>
                        {side === "mine" ? show(i.mine, i.mine_missing) : show(i.remote, i.remote_missing)}
                      </pre>
                    </label>
                  ))}
                </div>
              </div>
            ))}
            {left > 0 && <p className="vcs-hint">{left} choice(s) left.</p>}
            <div className="modal-buttons">
              <button onClick={onCancel}>Cancel</button>
              <button className="primary" disabled={left > 0} onClick={() => onSettle(chosen)}>
                Settle
              </button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
