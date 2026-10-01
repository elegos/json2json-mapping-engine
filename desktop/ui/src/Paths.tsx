import { type Diagnostic, type PathsSection, addAlias, renameEntry } from "./model";

interface Props {
  paths: PathsSection;
  /** Problems with the section (file-level diagnostics that start with "paths:"). */
  issues: Diagnostic[];
  onChange: (change: (paths: PathsSection) => void) => void;
}

/**
 * The `paths:` section of the file: what `$` stands for, and named paths (`@name`).
 * Every path here is written from the real document root; `@root` always reaches it.
 */
export function Paths({ paths, issues, onChange }: Props) {
  return (
    <div className="paths">
      <p className="config-help paths-help">
        Paths are written from the real document root. With a root set, <code>$</code> means that
        path in every rule; <code>@root</code> always reaches the real root. An alias is used as{" "}
        <code>@name.field</code>; its name cannot be a lookup, a loop label, <code>root</code> or{" "}
        <code>index</code>.
      </p>
      {issues.map((d, i) => (
        <div key={i} className={`lookup-issue ${d.severity}`}>
          {d.message.replace(/^paths: /, "")}
        </div>
      ))}
      <label className="paths-root">
        <span className="config-key">$ means</span>
        <input
          value={paths.root ?? ""}
          placeholder="(the document root)"
          onChange={(e) => onChange((p) => (p.root = e.target.value || null))}
        />
      </label>
      <h2>Aliases</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Path</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {Object.entries(paths.aliases).map(([name, target]) => (
            <tr key={name}>
              <td>
                <span className="muted">@</span>
                <input
                  defaultValue={name}
                  onBlur={(e) =>
                    onChange((p) => {
                      p.aliases = renameEntry(p.aliases, name, e.target.value) as Record<string, string>;
                    })
                  }
                />
              </td>
              <td>
                <input
                  value={target}
                  onChange={(e) => onChange((p) => (p.aliases = { ...p.aliases, [name]: e.target.value }))}
                />
              </td>
              <td>
                <button
                  title="Delete alias"
                  onClick={() =>
                    onChange((p) => {
                      p.aliases = Object.fromEntries(
                        Object.entries(p.aliases).filter(([k]) => k !== name),
                      );
                    })
                  }
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={() => onChange((p) => (p.aliases = addAlias(p.aliases)))}>+ Alias</button>
    </div>
  );
}
