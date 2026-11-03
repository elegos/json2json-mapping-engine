import { CodeEditor, type Completer } from "./CodeEditor";
import {
  type CheckSpec,
  type Diagnostic,
  type ValidationSide,
  type ValidationsSection,
  duplicateChecks,
  newCheck,
} from "./model";

interface Props {
  validations: ValidationsSection;
  /** The checker's findings, by the position they name (`validations.input.checks[0]`). */
  diagnostics: ReadonlyMap<string, Diagnostic[]>;
  onChange: (change: (section: ValidationsSection) => void) => void;
  /** Suggestions for an Expect cell, asked of the worker with the check's position. */
  complete?: (path: string, text: string, cursor: number) => ReturnType<Completer>;
}

const SIDES: { side: ValidationSide; title: string; about: string }[] = [
  { side: "input", title: "Input", about: "Run before any rule, on the document the mapping reads." },
  { side: "output", title: "Output", about: "Run after the last rule, on the document the mapping wrote." },
];

/**
 * The `validations:` section of the file: for each side, the JSON Schema check and the extra checks
 * (an expression on `$` that must be true; a failed one rejects the message or only warns).
 */
export function Validations({ validations, diagnostics, onChange, complete }: Props) {
  const dupIds = duplicateChecks(validations, "id");
  const dupCodes = duplicateChecks(validations, "code");
  return (
    <div className="paths validations">
      <p className="config-help paths-help">
        A <strong>reject</strong> check runs no rule and gives no output; a <strong>warn</strong> check only adds to
        the report. Only a <em>true</em> condition passes, and a comparison with a missing value is not true: write{" "}
        <code>not $.x or …</code> for an optional field. <code>id</code> and <code>code</code> are unique in the
        whole mapping, both sides together.
      </p>
      {SIDES.map(({ side, title, about }) => {
        const spec = validations[side];
        const edit = (change: (c: CheckSpec[]) => void) =>
          onChange((v) => change(v[side].checks));
        const sideIssues = diagnostics.get(`validations.${side}`) ?? [];
        return (
          <section key={side} aria-label={title}>
            <h2>{title}</h2>
            <p className="muted">{about}</p>
            {sideIssues.map((d, i) => (
              <div key={i} className={`lookup-issue ${d.severity}`}>
                {d.message}
              </div>
            ))}
            <label className="validation-schema">
              <input
                type="checkbox"
                checked={spec.schema}
                onChange={(e) => onChange((v) => (v[side].schema = e.target.checked))}
              />{" "}
              Validate against the mapping's JSON Schema
              <span className="muted">
                {" "}
                (best effort: Oracle does not check <code>format</code>; the host may validate upstream or
                downstream instead)
              </span>
            </label>
            {spec.checks.length > 0 && (
              <table>
                <thead>
                  <tr>
                    <th>Id</th>
                    <th>Expect (on $)</th>
                    <th>Code</th>
                    <th>Message</th>
                    <th>Action</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {spec.checks.map((c, i) => {
                    const issues = diagnostics.get(`validations.${side}.checks[${i}]`) ?? [];
                    const set = (patch: Partial<CheckSpec>) => edit((cs) => void Object.assign(cs[i], patch));
                    return [
                      <tr key={i}>
                        <td>
                          <input
                            value={c.id}
                            className={dupIds.has(c.id) ? "invalid" : undefined}
                            title={dupIds.has(c.id) ? "Another check has this id" : undefined}
                            onChange={(e) => set({ id: e.target.value })}
                          />
                        </td>
                        <td className="validation-expect">
                          <CodeEditor
                            className="check-expect"
                            value={c.expect}
                            completer={
                              complete
                                ? (text, cursor) => complete(`validations.${side}.checks[${i}]`, text, cursor)
                                : undefined
                            }
                            onChange={(text) => set({ expect: text })}
                          />
                        </td>
                        <td>
                          <input
                            value={c.code}
                            className={dupCodes.has(c.code) ? "invalid" : undefined}
                            title={dupCodes.has(c.code) ? "Another check has this code" : undefined}
                            onChange={(e) => set({ code: e.target.value })}
                          />
                        </td>
                        <td>
                          <input
                            value={c.message}
                            placeholder="(the code)"
                            onChange={(e) => set({ message: e.target.value })}
                          />
                        </td>
                        <td>
                          <select
                            value={c.action}
                            onChange={(e) => set({ action: e.target.value as CheckSpec["action"] })}
                          >
                            <option value="reject">reject</option>
                            <option value="warn">warn</option>
                          </select>
                        </td>
                        <td>
                          <button
                            title="Delete check"
                            onClick={() => edit((cs) => void cs.splice(i, 1))}
                          >
                            ✕
                          </button>
                        </td>
                      </tr>,
                      ...(c.expect.trim() === ""
                        ? [
                            <tr key={`${i}-empty`}>
                              <td colSpan={6} className="lookup-issue error">
                                Write the condition that must be true in Expect.
                              </td>
                            </tr>,
                          ]
                        : []),
                      ...(c.expect.trim() === "" ? [] : issues).map((d, k) => (
                        <tr key={`${i}-${k}`}>
                          <td colSpan={6} className={`lookup-issue ${d.severity}`}>
                            {d.message}
                          </td>
                        </tr>
                      )),
                    ];
                  })}
                </tbody>
              </table>
            )}
            <button onClick={() => onChange((v) => v[side].checks.push(newCheck(v)))}>+ Check</button>
          </section>
        );
      })}
    </div>
  );
}
