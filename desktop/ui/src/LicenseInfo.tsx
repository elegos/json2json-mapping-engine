import { createPortal } from "react-dom";

interface Props {
  onClose: () => void;
}

/** The "about box" the GPL recommends for a GUI: short notice, the generated-output
 * exception, and a pointer to the full LICENSE file. */
export function LicenseInfo({ onClose }: Props) {
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
      >
        <p>
          <strong>json2json-mapping-engine</strong>
          <br />
          Copyright (C) 2026 Giacomo Furlan
        </p>
        <p>
          This program comes with ABSOLUTELY NO WARRANTY. This is free software, licensed under
          the GNU General Public License v3.0 (GPLv3); see the <code>LICENSE</code> file in the
          project for the full text.
        </p>
        <p>
          <strong>Generated output exception:</strong> code produced from your mapping rules
          (PL/SQL, Python, or any other backend target) is not covered by the GPL and may be used
          under terms of your choosing — only the engine itself (compiler, transpiler, CLI,
          desktop tool) is GPLv3. The exact terms are at the end of the <code>LICENSE</code> file.
        </p>
        <div className="modal-buttons">
          <button className="primary" autoFocus onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
