import {
  type ConfigIssue,
  type ConfigOption,
  type ConfigSchema,
  type ConfigValues,
  issuesAt,
  setAt,
  shownValue,
  tableAt,
} from "./projectConfig";

interface Props {
  schema: ConfigSchema;
  values: ConfigValues;
  /** What `mapper.toml` holds now: a field that differs is shown as changed. */
  saved: ConfigValues;
  issues: ConfigIssue[];
  onChange: (values: ConfigValues) => void;
}

interface FieldProps {
  option: ConfigOption;
  table: Record<string, unknown>;
  changed: boolean;
  problems: string[];
  onSet: (value: unknown) => void;
}

function Field({ option, table, changed, problems, onSet }: FieldProps) {
  const value = shownValue(table, option);
  const placeholder = option.default === null || option.default === undefined ? "" : String(option.default);
  let control;
  switch (option.kind) {
    case "bool":
      control = <input type="checkbox" checked={value === true} onChange={(e) => onSet(e.target.checked)} />;
      break;
    case "choice":
      control = (
        <select value={String(value ?? "")} onChange={(e) => onSet(e.target.value)}>
          {value === undefined || value === null ? <option value="" /> : null}
          {option.choices.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      );
      break;
    case "int":
      control = (
        <input
          type="number"
          step={1}
          value={typeof table[option.key] === "number" ? (table[option.key] as number) : ""}
          placeholder={placeholder}
          onChange={(e) => onSet(e.target.value === "" ? undefined : Math.trunc(Number(e.target.value)))}
        />
      );
      break;
    case "table": {
      const rows = Object.entries(typeof value === "object" && value !== null ? (value as Record<string, string>) : {});
      const write = (next: [string, string][]) => onSet(next.length ? Object.fromEntries(next) : undefined);
      control = (
        <div className="config-table">
          {rows.map(([k, v], i) => (
            <div key={i} className="config-row">
              <input
                defaultValue={k}
                placeholder="key"
                onBlur={(e) => write(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))}
              />
              <input
                defaultValue={v}
                placeholder="value"
                onBlur={(e) => write(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))}
              />
              <button title="Remove" onClick={() => write(rows.filter((_, j) => j !== i))}>
                ✕
              </button>
            </div>
          ))}
          <button onClick={() => write([...rows, [`key${rows.length + 1}`, ""]])}>+ Row</button>
        </div>
      );
      break;
    }
    default:
      control = (
        <input
          value={typeof table[option.key] === "string" ? (table[option.key] as string) : ""}
          placeholder={placeholder}
          onChange={(e) => onSet(e.target.value === "" ? undefined : e.target.value)}
        />
      );
  }
  return (
    <div className={["config-field", problems.length ? "invalid" : "", changed ? "changed" : ""].join(" ").trim()}>
      <label>
        <span className="config-key">
          {option.key}
          {option.required ? " *" : ""}
        </span>
        {control}
      </label>
      {option.help && <div className="config-help">{option.help}</div>}
      {problems.map((p, i) => (
        <div key={i} className="config-problem">
          {p}
        </div>
      ))}
    </div>
  );
}

function Group(props: {
  title: string;
  path: string[];
  options: ConfigOption[];
  values: ConfigValues;
  saved: ConfigValues;
  issues: ConfigIssue[];
  onChange: (values: ConfigValues) => void;
}) {
  const table = tableAt(props.values, props.path);
  const savedTable = tableAt(props.saved, props.path);
  return (
    <fieldset>
      <legend>{props.title}</legend>
      {props.options.map((option) => (
        <Field
          key={option.key}
          option={option}
          table={table}
          changed={JSON.stringify(table[option.key]) !== JSON.stringify(savedTable[option.key])}
          problems={issuesAt(props.issues, props.path, option.key)}
          onSet={(value) => {
            let next = setAt(props.values, props.path, option.key, value);
            // choosing a target creates its section, so its required keys get reported
            if (props.path.join(".") === "project" && option.key === "target" && typeof value === "string") {
              if (!(value in tableAt(next, ["target"]))) next = setAt(next, ["target"], value, {});
            }
            props.onChange(next);
          }}
        />
      ))}
    </fieldset>
  );
}

/** Form for `mapper.toml`. The engine's sections and the active target's keys are drawn from
 * the descriptors of `schema`; the target's come from its backend. */
export function ProjectProperties({ schema, values, saved, issues, onChange }: Props) {
  const target = String(tableAt(values, ["project"]).target ?? "");
  const options = schema.targets[target];
  const testOptions = schema.target_tests?.[target];
  const general = issues.filter((i) => i.path === "");
  return (
    <div className="config">
      <h2>Project properties · mapper.toml</h2>
      {general.map((i, k) => (
        <div key={k} className="config-problem">
          {i.message}
        </div>
      ))}
      {schema.engine.map((section) => (
        <Group
          key={section.path.join(".")}
          title={section.title}
          path={section.path}
          options={section.options}
          values={values}
          saved={saved}
          issues={issues}
          onChange={onChange}
        />
      ))}
      {options ? (
        <Group
          title={`Target: ${target}`}
          path={["target", target]}
          options={options}
          values={values}
          saved={saved}
          issues={issues}
          onChange={onChange}
        />
      ) : (
        <fieldset>
          <legend>{`Target: ${target}`}</legend>
          <div className="config-help">
            This backend does not declare its options, so there is no form for them: edit the
            [target.{target}] section of mapper.toml by hand.
          </div>
        </fieldset>
      )}
      {testOptions && (
        <Group
          title={`Integration tests: ${target}`}
          path={["target", target, "test"]}
          options={testOptions}
          values={values}
          saved={saved}
          issues={issues}
          onChange={onChange}
        />
      )}
    </div>
  );
}
