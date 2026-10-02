import type { ColDef, ICellRendererParams, ValueSetterParams } from "ag-grid-community";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { AgGridReact } from "ag-grid-react";
import { type Choice, Confirm } from "./Confirm";
import { CompletingCellEditor, type GridContext } from "./CompletingCellEditor";
import { Lookups } from "./Lookups";
import { Paths } from "./Paths";
import { ProjectProperties } from "./ProjectProperties";
import { nameProblem } from "./mappings";
import { PromptDialog, type PromptField } from "./PromptDialog";
import { SchemaStatusButtons } from "./SchemaStatus";
import {
  type ConfigIssue,
  type ConfigSchema,
  type ConfigValues,
} from "./projectConfig";
import { ProjectButton } from "./ProjectButton";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  changeStructure,
  checkTree,
  completeAt,
  configCheck,
  configRead,
  configWrite,
  chooseProject,
  chooseSchemaFile,
  editTree,
  importSchema,
  mappingCreate,
  mappingDelete,
  mappingGolden,
  mappingRemoval,
  mappingRename,
  type SchemaKind,
  scaffoldRules,
  schemasStatus,
  type SchemasStatus,
  initialProject,
  listFnFiles,
  type CommandReport,
  type PythonStatus,
  pythonStatus,
  readFn,
  reviewEdit,
  runMapper,
  writeFn,
} from "./api";
import {
  changedColumns,
  columnOf,
  descendants,
  insertionPoint,
  diagnosticsByRule,
  expressionOf,
  filterByState,
  matchesState,
  filterRows,
  flatten,
  type Diagnostic,
  type FieldRule,
  type FunctionalFile,
  type LookupRule,
  isUnfinished,
  nameOf,
  pushRecent,
  rowIssues,
  savedIndex,
  treePrefix,
  visibleRows,
  ruleAt,
  reviewState,
  type ReviewState,
  setReviewState,
  VALIDATION_LABELS,
  type ReviewFlag,
  type Row,
  setExpression,
  sourceOf,
  STATE_FILTERS,
  targetPath,
  type StateFilter,
} from "./model";
import { MiddleEllipsis } from "./MiddleEllipsis";
import { OverridePane } from "./OverridePane";

// Boolean columns only make sense on field rules; elsewhere the cell stays empty.
const fieldOnly = (p: { data?: Row }) =>
  p.data?.rule.kind === "field" ? undefined : { component: () => null };

/** A boolean setting remembered across runs (per-viewer convenience only). */
function usePersisted(key: string): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => {
    try {
      return localStorage.getItem(key) === "1";
    } catch {
      return false;
    }
  });
  const set = (next: boolean) => {
    setValue(next);
    try {
      localStorage.setItem(key, next ? "1" : "0");
    } catch {
      /* not persisted */
    }
  };
  return [value, set];
}

function loadRecent(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem("recentProjects") ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((d): d is string => typeof d === "string") : [];
  } catch {
    return [];
  }
}

/** The name the tool shows for a mapping: `orders`, not `mappings/functional/orders.fn.yaml`. */
function mappingName(file: string): string {
  return file.replace(/^.*\//, "").replace(/\.fn\.yaml$/, "");
}

const COMMANDS = ["transpile", "build", "check"] as const;

export function App() {
  const [python, setPython] = useState<PythonStatus | null>(null);
  const [project, setProject] = useState<string | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [tree, setTree] = useState<FunctionalFile | null>(null);
  const [saved, setSaved] = useState("");
  const [report, setReport] = useState<CommandReport | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<Diagnostic[]>([]);
  // the mapping's input / output schemas as found on disk; `schemaTick` asks for a new look
  const [schemas, setSchemas] = useState<SchemasStatus | null>(null);
  const [schemaTick, setSchemaTick] = useState(0);
  const [recent, setRecent] = useState<string[]>(loadRecent);
  const grid = useRef<AgGridReact<Row>>(null);
  const [question, setQuestion] = useState<{
    message: string;
    choices: Choice[];
    option?: string;
    resolve: (id: string, checked: boolean) => void;
  } | null>(null);
  const [prompt, setPrompt] = useState<{
    title: string;
    fields: PromptField[];
    confirm: string;
    validate: (values: Record<string, string>) => string | null;
    resolve: (values: Record<string, string> | null) => void;
  } | null>(null);
  const dirtyRef = useRef(false);
  const saveRef = useRef<() => Promise<boolean>>(async () => true);
  const folding = useRef(false);
  const treeRef = useRef<FunctionalFile | null>(null);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [filterText, setFilterText] = useState("");
  const [stateFilter, setStateFilter] = useState<StateFilter>("all");
  const [flags, setFlags] = useState<ReadonlyMap<string, ReviewFlag>>(new Map());
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const filterInput = useRef<HTMLInputElement>(null);
  const [view, setView] = useState<"rules" | "lookups" | "paths" | "project">("rules");
  // mapper.toml: the form's descriptors, the file's values, the draft being edited
  const [configSchema, setConfigSchema] = useState<ConfigSchema | null>(null);
  const [configSaved, setConfigSaved] = useState("");
  const [config, setConfig] = useState<ConfigValues | null>(null);
  const [configIssues, setConfigIssues] = useState<ConfigIssue[]>([]);
  // undo / redo: snapshots of what the user can edit (the rules and the mapper.toml draft)
  type Snapshot = { tree: FunctionalFile | null; config: ConfigValues | null };
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const configRef = useRef<ConfigValues | null>(null);
  const lastEdit = useRef({ key: "", at: 0 });
  const [, setHistoryVersion] = useState(0);
  const [showIds, setShowIds] = usePersisted("showRuleIds");
  const [developerMode, setDeveloperMode] = usePersisted("developerMode");
  useEffect(() => {
    // validation states are a developer's matter: leaving the mode leaves their filter
    if (!developerMode) setStateFilter((f) => (f === "all" || f === "invalid" ? f : "all"));
  }, [developerMode]);

  useEffect(() => {
    pythonStatus().then(setPython, (e) => setStatus(String(e)));
  }, []);

  treeRef.current = tree;
  configRef.current = config;
  const fnDirty = tree !== null && JSON.stringify(tree) !== saved;
  const configDirty = config !== null && JSON.stringify(config) !== configSaved;
  const dirty = fnDirty || configDirty;
  dirtyRef.current = dirty;

  /**
   * Remember the state before a change. Edits with the same `key` in quick succession
   * (typing in one field) count as one step.
   */
  const remember = useCallback((before: FunctionalFile | null = treeRef.current, key = "") => {
    const now = Date.now();
    const same = key !== "" && lastEdit.current.key === key && now - lastEdit.current.at < 800;
    lastEdit.current = { key, at: now };
    if (!same) past.current.push({ tree: before, config: configRef.current });
    future.current = [];
    setHistoryVersion((v) => v + 1);
  }, []);
  const forgetHistory = useCallback(() => {
    past.current = [];
    future.current = [];
    lastEdit.current = { key: "", at: 0 };
    setHistoryVersion((v) => v + 1);
  }, []);
  const travel = useCallback((from: Snapshot[], to: Snapshot[]) => {
    const target = from.pop();
    if (!target) return;
    to.push({ tree: treeRef.current, config: configRef.current });
    lastEdit.current = { key: "", at: 0 };
    setTree(target.tree);
    if (target.config && configRef.current) setConfig(target.config);
    setHistoryVersion((v) => v + 1);
  }, []);
  const undo = useCallback(() => travel(past.current, future.current), [travel]);
  const redo = useCallback(() => travel(future.current, past.current), [travel]);
  const canUndo = past.current.length > 0;
  const canRedo = future.current.length > 0;

  const ask = useCallback(
    (message: string, choices: Choice[]) =>
      new Promise<string>((resolve) => setQuestion({ message, choices, resolve: (id) => resolve(id) })),
    [],
  );
  /** A question with a checkbox: resolves to the choice and whether the box was ticked. */
  const askWithOption = useCallback(
    (message: string, choices: Choice[], option?: string) =>
      new Promise<{ id: string; checked: boolean }>((resolve) =>
        setQuestion({ message, choices, option, resolve: (id, checked) => resolve({ id, checked }) }),
      ),
    [],
  );

  /** True when it is fine to go on: nothing unsaved, or the user saved / chose to discard. */
  const guardUnsaved = useCallback(
    async (message: string, discardLabel: string): Promise<boolean> => {
      if (!dirtyRef.current) return true;
      const choice = await ask(message, [
        { id: "save", label: "Save", primary: true },
        { id: "discard", label: discardLabel },
        { id: "cancel", label: "Cancel" },
      ]);
      if (choice === "save") return saveRef.current();
      return choice === "discard";
    },
    [ask],
  );
  const guardRef = useRef(guardUnsaved);
  guardRef.current = guardUnsaved;

  // closing the window with unsaved changes
  useEffect(() => {
    const window = getCurrentWindow();
    const unlisten = window.onCloseRequested(async (event) => {
      if (!dirtyRef.current) return;
      event.preventDefault();
      const ok = await guardRef.current(
        "Save the document? If you close without saving you will lose your changes.",
        "Close without saving",
      );
      if (ok) await window.destroy();
    });
    return () => {
      void unlisten.then((fn) => fn());
    };
  }, []);
  const canBuild = python?.available === true && project !== null && !busy;

  const load = useCallback(
    async (file: string, keepHistory = false) => {
      if (!project) return;
      try {
        const loaded = await readFn(project, file);
        if (!keepHistory) forgetHistory();
        setCurrent(file);
        setTree(loaded);
        setSaved(JSON.stringify(loaded));
        setStatus("");
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [project, forgetHistory],
  );

  const openDir = useCallback(async (dir: string) => {
    try {
      const found = await listFnFiles(dir);
      setProject(dir);
      forgetHistory();
      setConfig(null);
      setConfigSchema(null);
      setView("rules");
      setCollapsed(new Set());
      setRecent((old) => {
        const next = pushRecent(old, dir);
        try {
          localStorage.setItem("recentProjects", JSON.stringify(next));
        } catch {
          /* not persisted */
        }
        return next;
      });
      setFiles(found);
      setCurrent(null);
      setTree(null);
      setReport(null);
      setStatus(found.length ? "" : "no mappings/functional/*.fn.yaml in this project");
      if (found.length) {
        const first = await readFn(dir, found[0]);
        setCurrent(found[0]);
        setTree(first);
        setSaved(JSON.stringify(first));
      }
    } catch (e) {
      setStatus(String(e));
    }
  }, [forgetHistory]);

  const askValues = useCallback(
    (title: string, fields: PromptField[], confirm: string, validate: (v: Record<string, string>) => string | null) =>
      new Promise<Record<string, string> | null>((resolve) =>
        setPrompt({ title, fields, confirm, validate, resolve }),
      ),
    [],
  );

  /** The list of mappings again, then the one called `select` (else the first) is opened. */
  const reloadFiles = useCallback(
    async (select: string | null) => {
      if (!project) return;
      const found = await listFnFiles(project);
      setFiles(found);
      const wanted = found.find((f) => select !== null && mappingName(f) === select) ?? found[0];
      if (wanted) {
        await load(wanted);
      } else {
        setCurrent(null);
        setTree(null);
        setStatus("no mappings/functional/*.fn.yaml in this project");
      }
    },
    [project, load],
  );

  const switchGuard = useCallback(
    () => guardRef.current("Save the current file before switching? Your unsaved changes will be lost otherwise.", "Discard changes"),
    [],
  );

  const newMapping = useCallback(async () => {
    if (!project || !(await switchGuard())) return;
    const taken = files.map(mappingName);
    let name = "";
    try {
      for (;;) {
        const got = await askValues(
          "New mapping",
          [{ key: "name", label: "Name", value: name, hint: "It names the file, its schemas and the PL/SQL package." }],
          "Create",
          (v) => nameProblem(v.name.trim(), taken),
        );
        if (!got) return;
        name = got.name.trim();
        // a mapping deleted earlier leaves its golden cases: they are not taken over unasked
        const golden = await mappingGolden(project, name);
        let how: "keep" | "rename" | "delete" | undefined;
        let to: string | undefined;
        if (golden.files > 0) {
          const choice = await ask(
            `${golden.path}/ already holds ${golden.files} file${golden.files === 1 ? "" : "s"} (golden cases of a mapping that was called ${name}). What should happen to them?`,
            [
              { id: "keep", label: "Use them for the new mapping" },
              { id: "rename", label: "Rename the folder…" },
              { id: "delete", label: "Delete them" },
              { id: "name", label: "Choose another name", primary: true },
            ],
          );
          if (choice === "name") continue;
          if (choice === "rename") {
            const moved = await askValues(
              "Rename the golden folder",
              [{ key: "to", label: `New name of ${golden.path}`, value: golden.suggest }],
              "Rename",
              (v) => (/^[A-Za-z0-9_][A-Za-z0-9_.-]*$/.test(v.to.trim()) ? null : "Letters, digits, _ . and -, no slashes."),
            );
            if (!moved) continue;
            to = moved.to.trim();
          }
          if (choice === "delete") {
            const sure = await ask(
              `Delete ${golden.path}/ with its ${golden.files} file${golden.files === 1 ? "" : "s"}? They stay in git history if they were committed.`,
              [
                { id: "delete", label: "Delete" },
                { id: "cancel", label: "Cancel", primary: true },
              ],
            );
            if (sure !== "delete") continue;
          }
          how = choice as "keep" | "rename" | "delete";
        }
        await mappingCreate(project, name, how, to);
        await reloadFiles(name);
        return;
      }
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, files, switchGuard, askValues, ask, reloadFiles]);

  const renameCurrent = useCallback(async () => {
    if (!project || !current || !tree || !(await switchGuard())) return;
    const old = mappingName(current);
    const others = files.map(mappingName).filter((n) => n !== old);
    const got = await askValues(
      "Rename mapping",
      [
        { key: "name", label: "Name", value: old },
        {
          key: "id",
          label: "Id",
          value: tree.id,
          hint: "It names the PL/SQL package. It follows the name while it is the old name; change it to pick your own.",
        },
      ],
      "Rename",
      (v) =>
        nameProblem(v.name.trim(), others) ??
        (nameProblem(v.id.trim(), []) ? "The id: letters, digits and _, not starting with a digit." : null),
    );
    if (!got) return;
    const to = got.name.trim();
    const id = got.id.trim();
    try {
      await mappingRename(project, old, to, id !== tree.id ? id : undefined);
      await reloadFiles(to);
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, current, tree, files, switchGuard, askValues, reloadFiles]);

  const deleteCurrent = useCallback(async () => {
    if (!project || !current) return;
    const name = mappingName(current);
    try {
      const { files: plan } = await mappingRemoval(project, name);
      const golden = await mappingGolden(project, name);
      const { id: choice, checked } = await askWithOption(
        `Delete the mapping '${name}'? This removes:\n${plan.map((f) => `  ${f}`).join("\n")}\n\n` +
          "The compiled packages go at the next build. Unsaved changes in it are lost.",
        [
          // the last choice is what Escape answers, and the one focused
          { id: "delete", label: "Delete" },
          { id: "cancel", label: "Cancel", primary: true },
        ],
        golden.files > 0
          ? `Delete also the golden records (${golden.files} file${golden.files === 1 ? "" : "s"})`
          : undefined,
      );
      if (choice !== "delete") return;
      await mappingDelete(project, name, checked && golden.files > 0);
      await reloadFiles(null);
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, current, askWithOption, reloadFiles]);

  const openProject = useCallback(async () => {
    if (!(await switchGuard())) return;
    const dir = await chooseProject(recent[0]);
    if (dir) await openDir(dir);
  }, [openDir, recent, switchGuard]);

  useEffect(() => {
    initialProject().then(
      (dir) => {
        if (dir) void openDir(dir);
      },
      () => {},
    );
  }, [openDir]);

  const save = useCallback(async (): Promise<boolean> => {
    if (!project) return true;
    setBusy(true);
    try {
      let decayed: string[] = [];
      if (current && tree && fnDirty) {
        decayed = await writeFn(project, current, tree);
        await load(current, true);
      }
      if (config && configDirty) {
        await configWrite(project, config);
        const again = await configRead(project);
        setConfig(again.values);
        setConfigSaved(JSON.stringify(again.values));
      }
      setStatus(
        decayed.length
          ? `saved; validation reset on: ${decayed.join(", ")}`
          : "saved",
      );
      return true;
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
      return false;
    } finally {
      setBusy(false);
    }
  }, [project, current, tree, load, config, fnDirty, configDirty]);
  saveRef.current = save;

  const run = useCallback(
    async (command: string) => {
      if (!project) return;
      // the commands read the files on disk, not what is in the grid
      if (!(await guardRef.current("Save before continuing?", "Continue without saving"))) return;
      setBusy(true);
      try {
        setReport(await runMapper(project, command));
      } catch (e) {
        setStatus(String(e));
      } finally {
        setBusy(false);
      }
    },
    [project],
  );

  // typing outside an editor goes to the filter: its text is what the user means to enter
  const rulesShown = tree !== null && view === "rules";
  useEffect(() => {
    if (!rulesShown) return;
    const onType = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey || e.isComposing || e.key.length !== 1) return;
      const input = filterInput.current;
      if (!input || question || document.activeElement === input) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], .cm-editor")) return;
      if (e.key === " " && !filterText.trim()) return; // Space on a cell is the cell's
      // before the grid sees it (it would start editing the cell); the character then lands in
      // the field that has just been focused
      e.stopPropagation();
      input.focus();
    };
    window.addEventListener("keydown", onType, true);
    return () => window.removeEventListener("keydown", onType, true);
  }, [rulesShown, question, filterText]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (dirty && !busy) void save();
        return;
      }
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      // inside a text field the field's own undo applies
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      const key = e.key.toLowerCase();
      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (key === "y" || (key === "z" && e.shiftKey)) {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dirty, busy, save, undo, redo]);

  const edit = useCallback((path: string, change: (rule: NonNullable<ReturnType<typeof ruleAt>>) => void, key = "") => {
    remember(treeRef.current, key);
    setTree((old) => {
      if (!old) return old;
      const copy = structuredClone(old);
      const rule = ruleAt(copy, path);
      if (rule) change(rule);
      return copy;
    });
  }, [remember]);

  const editPaths = useCallback(
    (change: (paths: NonNullable<FunctionalFile["paths"]>) => void) => {
      remember(treeRef.current, "paths");
      setTree((old) => {
        if (!old) return old;
        const copy = structuredClone(old);
        change(copy.paths);
        return copy;
      });
    },
    [remember],
  );

  /** Target / Source edits are done by the Python worker (one implementation of the path rules). */
  const remoteEdit = useCallback(
    async (op: "retarget" | "set_source", path: string, value: string) => {
      const current = treeRef.current;
      if (!current) return;
      try {
        const next = await editTree(current, op, path, value);
        remember(current);
        setTree(next);
        setStatus("");
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [remember],
  );

  /** Overrides and validation: also done by the worker (it knows the generated code and the functions). */
  const reviewOp = useCallback(
    async (
      op: "take_over" | "accept_proposal" | "keep_override",
      path: string,
    ) => {
      const current = treeRef.current;
      if (!current) return;
      try {
        const next = await reviewEdit(current, op, path);
        remember(current);
        setTree(next);
        setStatus("");
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [remember],
  );

  const openProperties = useCallback(async () => {
    if (!project) return;
    try {
      if (!config) {
        const read = await configRead(project);
        setConfigSchema(read.schema);
        setConfig(read.values);
        setConfigSaved(JSON.stringify(read.values));
      }
      setView("project");
      setStatus("");
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, config]);

  // check the draft of mapper.toml as it is edited
  useEffect(() => {
    if (!config) {
      setConfigIssues([]);
      return;
    }
    let stale = false;
    const timer = setTimeout(() => {
      configCheck(config).then(
        (found) => {
          if (!stale) setConfigIssues(found);
        },
        () => {},
      );
    }, 150);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [config]);

  const selectedRow = () => grid.current?.api?.getSelectedRows()[0];

  const addRule = useCallback(async (kind: string, atRoot = false) => {
    const current = treeRef.current;
    if (!current) return;
    const at = atRoot ? { parent: null, index: null } : insertionPoint(selectedRow());
    try {
      const next = await changeStructure(current, { op: "add_rule", ...at, kind });
      remember(current);
      setTree(next);
      if (at.parent) setCollapsed((old) => new Set([...old].filter((p) => p !== at.parent)));
      setStatus("");
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [remember]);

  const deleteRule = useCallback(async (path?: string) => {
    const current = treeRef.current;
    const row = path
      ? flatten(current?.rules ?? []).find((r) => r.path === path)
      : selectedRow();
    if (!current || !row) return;
    const below = descendants(row.rule);
    if (below > 0) {
      const choice = await ask(
        `Delete "${nameOf(row.rule)}" and the ${below} rule${below === 1 ? "" : "s"} inside it?`,
        [
          { id: "delete", label: "Delete", primary: true },
          { id: "cancel", label: "Cancel" },
        ],
      );
      if (choice !== "delete") return;
    }
    try {
      const next = await changeStructure(current, { op: "delete_rule", path: row.path });
      remember(current);
      setTree(next);
      setStatus("");
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [ask, remember]);

  const toggleFold = useCallback((path: string) => {
    setCollapsed((old) => {
      const next = new Set(old);
      if (!next.delete(path)) next.add(path);
      return next;
    });
  }, []);
  // check the rules as they are edited (debounced), against the project's schemas
  useEffect(() => {
    if (!tree || !project || !current || python?.available !== true) {
      setLive([]);
      setFlags(new Map());
      return;
    }
    const stem = mappingName(current);
    let stale = false;
    const timer = setTimeout(() => {
      checkTree(tree, project, stem).then(
        (found) => {
          // same findings: keep the array, or the grid redraws (and closes an open editor)
          if (stale) return;
          setLive((old) => (JSON.stringify(old) === JSON.stringify(found.diagnostics) ? old : found.diagnostics));
          setFlags((old) => {
            const next = new Map(found.review.map((f) => [f.rule, f] as const));
            return JSON.stringify([...old]) === JSON.stringify([...next]) ? old : next;
          });
        },
        () => {},
      );
    }, 150);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [tree, project, current, python, schemaTick]);

  // are the mapping's schemas there? (a `schemas:` change in the file counts too)
  const schemaRefs = JSON.stringify(tree?.schemas ?? null);
  useEffect(() => {
    const open = treeRef.current;
    if (!open || !project || !current || python?.available !== true) {
      setSchemas(null);
      return;
    }
    let stale = false;
    schemasStatus(open, project, mappingName(current)).then(
      (found) => !stale && setSchemas({ input: found.input, output: found.output }),
      () => !stale && setSchemas(null),
    );
    return () => {
      stale = true;
    };
  }, [project, current, python, schemaRefs, schemaTick]);

  /** Loads (or replaces) the input / output schema: the file is copied into the project under the
   * mapping's name, so the mapping reads the copy; a `schemas:` override in the file would hide
   * it, so it is dropped (the file is then unsaved, as for any edit). */
  const pickSchema = useCallback(
    async (kind: SchemaKind) => {
      const open = treeRef.current;
      if (!open || !project || !current) return;
      try {
        const source = await chooseSchemaFile(kind, project);
        if (!source) return;
        const stem = mappingName(current);
        await importSchema(project, stem, kind, source);
        let next = open;
        if (open.schemas[kind]) {
          remember(open, "schemas");
          next = { ...open, schemas: { ...open.schemas, [kind]: null } };
          setTree((old) => (old ? { ...old, schemas: { ...old.schemas, [kind]: null } } : old));
        }
        setSchemaTick((n) => n + 1);
        setStatus("");
        // a new output schema: offer the rules it describes, empty, for the user to fill in
        if (kind === "output") {
          const found = await scaffoldRules(next, project, stem, false);
          if (found.added > 0) {
            const left =
              found.skipped.length > 0
                ? ` ${found.skipped.length} cannot be laid out (${found.skipped.slice(0, 3).join("; ")}${found.skipped.length > 3 ? "; …" : ""}).`
                : "";
            const choice = await ask(
              `Create ${found.added} empty rule${found.added === 1 ? "" : "s"} from the output schema? ` +
                `They are ignored until a Source is defined.${left}`,
              [
                { id: "create", label: "Create the rules", primary: true },
                { id: "no", label: "Not now" },
              ],
            );
            if (choice === "create") {
              const made = await scaffoldRules(next, project, stem, true);
              if (made.tree) {
                remember(next, "scaffold");
                setTree(made.tree);
              }
            }
          }
        }
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [project, current, remember, ask],
  );

  // what differs from the saved file, per row path ("*" = a new rule)
  const changes = useMemo(() => {
    const found = new Map<string, Set<string>>();
    if (!tree || !saved) return found;
    const before = savedIndex((JSON.parse(saved) as FunctionalFile).rules);
    for (const row of flatten(tree.rules)) {
      const old = row.rule.id
        ? before.byId.get(row.rule.id)
        : (() => {
            const same = before.byPath.get(row.path);
            return same && !same.id ? same : undefined;
          })();
      const cols = changedColumns(row.rule, old);
      if (cols.size) found.set(row.path, cols);
    }
    return found;
  }, [tree, saved]);

  const diagnostics = useMemo(
    () =>
      diagnosticsByRule(
        [...live, ...(current && report ? report.diagnostics : [])],
        current ?? "",
      ),
    [current, report, live],
  );

  const selectedRule = tree && selectedPath ? ruleAt(tree, selectedPath) : undefined;

  const rows = useMemo(
    // lookups have their own view
    () => {
      if (!tree) return [];
      const all = flatten(tree.rules).filter((r) => r.rule.kind !== "lookup");
      // a filter shows what it finds, folded or not
      const found = filterByState(all, stateFilter, flags, diagnostics);
      return filterText.trim() || stateFilter !== "all"
        ? filterRows(found, filterText)
        : visibleRows(all, collapsed);
    },
    [tree, collapsed, filterText, stateFilter, flags, diagnostics],
  );

  /** Columns (by colId) with an error on this row; "*" = the whole row. */
  const invalidColumns = useCallback(
    (path: string): Set<string> => {
      const found = new Set<string>();
      for (const d of diagnostics.get(path) ?? []) {
        if (d.severity === "error") found.add(columnOf(d) ?? "*");
      }
      return found;
    },
    [diagnostics],
  );

  // row / cell classes are computed from the diagnostics: redraw when they change
  useEffect(() => {
    const api = grid.current?.api;
    // never under an open editor: redrawing the row would close it
    if (api && api.getEditingCells().length === 0) api.redrawRows();
  }, [diagnostics, changes, flags]);

  // suggestions for the cell being edited: the Python worker knows the schemas and the scope
  const gridContext = useMemo<GridContext>(
    () => ({
      complete: async (path, column, text, cursor) => {
        const now = treeRef.current;
        if (!now || !project || !current || python?.available !== true) {
          return { from: cursor, items: [] };
        }
        const stem = mappingName(current);
        try {
          return await completeAt(now, project, stem, { path, column, text, cursor });
        } catch {
          return { from: cursor, items: [] };
        }
      },
    }),
    [project, current, python],
  );

  const columns = useMemo<ColDef<Row>[]>(() => {
    const editableFor = (kinds: string[]) => (p: { data?: Row }) =>
      p.data !== undefined && kinds.includes(p.data.rule.kind);
    return [
      {
        headerName: "",
        colId: "warn",
        width: 56,
        pinned: "left",
        sortable: false,
        resizable: false,
        cellClass: "warn-cell",
        valueGetter: (p) =>
          p.data && rowIssues(p.data.rule, diagnostics.get(p.data.path) ?? [], developerMode ? flags.get(p.data.path) : undefined, developerMode).length ? "⚠️" : "",
        tooltipValueGetter: (p) =>
          p.data ? rowIssues(p.data.rule, diagnostics.get(p.data.path) ?? [], developerMode ? flags.get(p.data.path) : undefined, developerMode).join("\n") : "",
      },
      { headerName: "Id", colId: "id", hide: !showIds, valueGetter: (p) => p.data?.rule.id ?? "", width: 100 },
      {
        headerName: "Target",
        colId: "target",
        width: 200,
        editable: (p) => !folding.current && p.data?.rule.kind !== "lookup",
        cellEditor: CompletingCellEditor,
        valueGetter: (p) => (p.data ? nameOf(p.data.rule) : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          void remoteEdit("retarget", p.data.path, String(p.newValue ?? ""));
          return true;
        },
        cellRenderer: (p: ICellRendererParams<Row>) =>
          p.data ? (
            <span>
              <span className="tree">{treePrefix(p.data)}</span>
              {p.data.hasChildren ? (
                <span
                  className="fold"
                  title={collapsed.has(p.data.path) ? "Expand" : "Collapse"}
                  onMouseDown={() => {
                    // the grid starts editing on the click that follows; tell it not to
                    folding.current = true;
                    setTimeout(() => (folding.current = false), 300);
                  }}
                  onClick={() => toggleFold(p.data!.path)}
                >
                  {collapsed.has(p.data.path) ? "▸" : "▾"}
                </span>
              ) : null}
              {p.value}
            </span>
          ) : null,
      },
      { headerName: "Kind",
        colId: "kind", valueGetter: (p) => p.data?.rule.kind, width: 80 },
      {
        headerName: "Type",
        colId: "type",
        width: 90,
        editable: editableFor(["field"]),
        cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: ["str", "int", "number", "bool", "date", "datetime"] },
        valueGetter: (p) => {
          const rule = p.data?.rule;
          if (rule?.kind === "field") return rule.type;
          return rule?.kind === "loop" ? "array" : rule?.kind === "object" ? "object" : "";
        },
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.type = String(p.newValue);
          });
          return true;
        },
      },
      {
        headerName: "Req.",
        colId: "req",
        width: 70,
        editable: editableFor(["field"]),
        cellDataType: "boolean",
        cellRendererSelector: fieldOnly,
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.required : null),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.required = Boolean(p.newValue);
          });
          return true;
        },
      },
      {
        headerName: "Source",
        colId: "source",
        width: 200,
        editable: editableFor(["field", "loop", "object"]),
        cellEditor: CompletingCellEditor,
        valueGetter: (p) => (p.data ? sourceOf(p.data.rule) : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          void remoteEdit("set_source", p.data.path, String(p.newValue ?? ""));
          return true;
        },
      },
      {
        headerName: "Expression / filter / guard",
        colId: "expression",
        flex: 1,
        minWidth: 260,
        cellEditor: CompletingCellEditor,
        // an object that selects an element by its Source has no guard
        editable: (p) =>
          p.data !== undefined &&
          (p.data.rule.kind === "object" ? !p.data.rule.source : ["field", "loop"].includes(p.data.rule.kind)),
        valueGetter: (p) => (p.data ? expressionOf(p.data.rule) : ""),
        // no expression: a field takes its Source value as it is
        cellRenderer: (p: ICellRendererParams<Row>) =>
          !p.value && p.data?.rule.kind === "field" && sourceOf(p.data.rule) ? (
            <span className="muted">= Source value</span>
          ) : (
            p.value
          ),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => setExpression(r, String(p.newValue ?? "")));
          return true;
        },
      },
      {
        headerName: "Description",
        colId: "description",
        width: 260,
        editable: true,
        valueGetter: (p) => p.data?.rule.description ?? "",
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            r.description = String(p.newValue ?? "") || null;
          });
          return true;
        },
      },
      {
        headerName: "Status",
        colId: "status",
        hide: !developerMode,
        width: 80,
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.transform.status : ""),
      },
      {
        headerName: "Validation",
        colId: "validation",
        hide: !developerMode,
        width: 130,
        editable: editableFor(["field"]),
        cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: Object.values(VALIDATION_LABELS) },
        valueGetter: (p) => (p.data?.rule.kind === "field" ? VALIDATION_LABELS[reviewState(p.data.rule)] : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          const state = (Object.keys(VALIDATION_LABELS) as ReviewState[]).find(
            (k) => VALIDATION_LABELS[k] === p.newValue,
          );
          if (state === "validated" && invalidColumns(p.data.path).size > 0) {
            setStatus("A rule with errors cannot be validated: fix them first.");
            return false;
          }
          if (state) edit(p.data.path, (r) => setReviewState(r, state));
          return true;
        },
      },
      {
        headerName: "Notes",
        colId: "notes",
        width: 220,
        editable: editableFor(["field"]),
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.validation.notes ?? "" : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.validation.notes = String(p.newValue ?? "") || null;
          });
          return true;
        },
      },
    ];
  }, [edit, remoteEdit, showIds, developerMode, diagnostics, flags, invalidColumns, collapsed, toggleFold]);

  return (
    <div className="app">
      <header>
        <ProjectButton recent={recent} onOpen={openProject} onPick={async (d) => {
            if (await switchGuard()) await openDir(d);
          }} />
        <MiddleEllipsis className="project" text={project ?? "no project"} />
        <button className="history" title="Undo (Ctrl + Z)" disabled={!canUndo || busy} onClick={undo}>
          ↶
        </button>
        <button className="history" title="Redo (Ctrl + Y)" disabled={!canRedo || busy} onClick={redo}>
          ↷
        </button>
        <button disabled={!dirty || busy} onClick={() => void save()}>
          Save{dirty ? " ●" : ""}
        </button>
        {COMMANDS.map((c) => (
          <button key={c} disabled={!canBuild} onClick={() => run(c)}>
            {c[0].toUpperCase() + c.slice(1)}
          </button>
        ))}
      </header>
      {python && !python.available && (
        <div className="banner">
          Read-only: {python.reason} Build, check and save are disabled.
        </div>
      )}
      <div className="body">
        <nav>
          <button
            className="project-properties"
            disabled={!project}
            onClick={() => void openProperties()}
          >
            Project properties…
          </button>
          <button className="new-mapping" disabled={!project} onClick={() => void newMapping()}>
            + New mapping…
          </button>
          {files.map((f) => (
            <div
              key={f}
              className={f === current ? "file current" : "file"}
              onClick={async () => {
                if (f !== current && (await switchGuard())) await load(f);
              }}
            >
              <span className="file-name">
                {mappingName(f)}
                {f === current && fnDirty ? "*" : ""}
              </span>
              {f === current && (
                <span className="file-actions">
                  <button title="Rename…" onClick={(e) => { e.stopPropagation(); void renameCurrent(); }}>✎</button>
                  <button title="Delete…" onClick={(e) => { e.stopPropagation(); void deleteCurrent(); }}>✕</button>
                </span>
              )}
            </div>
          ))}
        </nav>
        <main>
          {(tree || config) && (
            <div className="tabs">
              <button className={view === "rules" ? "tab active" : "tab"} onClick={() => setView("rules")}>
                Rules
              </button>
              <button className={view === "lookups" ? "tab active" : "tab"} onClick={() => setView("lookups")}>
                Lookups
              </button>
              <button className={view === "paths" ? "tab active" : "tab"} onClick={() => setView("paths")}>
                Paths
              </button>
              {/* the properties are a page of their own: a tab while they are open, or while they hold
                  changes not saved yet (so it is clear that mapper.toml is among them); gone once the
                  user goes elsewhere with nothing pending */}
              {config && (view === "project" || configDirty) && (
                <button className={view === "project" ? "tab active" : "tab"} onClick={() => setView("project")}>
                  Project properties{configDirty ? " ●" : ""}
                </button>
              )}
            </div>
          )}
          {view === "project" && config && configSchema && (
            <ProjectProperties
              schema={configSchema}
              values={config}
              saved={JSON.parse(configSaved) as ConfigValues}
              issues={configIssues}
              onChange={(next) => {
                remember(treeRef.current, "config");
                setConfig(next);
              }}
            />
          )}
          {tree && view === "paths" && (
            <Paths
              paths={tree.paths}
              issues={(diagnostics.get("") ?? []).filter((d) => d.message.startsWith("paths:"))}
              onChange={editPaths}
            />
          )}
          {tree && view === "lookups" && (
            <Lookups
              tree={tree}
              diagnostics={diagnostics}
              onEdit={(path, change) =>
                edit(
                  path,
                  (r) => {
                    if (r.kind === "lookup") change(r as LookupRule);
                  },
                  `lookup:${path}`,
                )
              }
              onAdd={() => void addRule("lookup", true)}
              onDelete={(path) => void deleteRule(path)}
            />
          )}
          {tree && view === "rules" && (
            <div className="toolbar">
              <button onClick={() => void addRule("field")}>+ Field</button>
              <button onClick={() => void addRule("object")}>+ Object</button>
              <button onClick={() => void addRule("loop")}>+ Loop</button>
              <button onClick={() => void deleteRule()}>Delete</button>
              <select
                className="state-filter"
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value as StateFilter)}
                title="Show only the rules in a state"
              >
                {STATE_FILTERS.filter(([id]) => developerMode || id === "all" || id === "invalid").map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                    {id !== "all" && id !== "invalid" ? ` (${[...flatten(tree.rules)].filter((r) => matchesState(r, id, flags, diagnostics)).length})` : ""}
                  </option>
                ))}
              </select>
              <input
                ref={filterInput}
                className="rule-filter"
                type="search"
                placeholder="Filter by rule id or target (customer.name, cusnam)"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && setFilterText("")}
              />
              <SchemaStatusButtons status={schemas} onPick={(kind) => void pickSchema(kind)} />
            </div>
          )}
          {tree && view === "rules" ? (
            <>
            <div className="grid">
            <AgGridReact<Row>
              rowData={rows}
              columnDefs={columns}
              getRowId={(p) => p.data.path}
              ref={grid}
              tooltipShowDelay={200}
              context={gridContext}
              defaultColDef={{
                sortable: false,
                cellClassRules: {
                  "cell-invalid": (p) => {
                    const cols = invalidColumns(p.data?.path ?? "");
                    return cols.has(p.column.getColId()) || cols.has("*");
                  },
                  "cell-changed": (p) => {
                    const cols = changes.get(p.data?.path ?? "");
                    return !!cols && (cols.has("*") || cols.has(p.column.getColId()));
                  },
                },
              }}
              singleClickEdit
              rowSelection={{ mode: "singleRow", checkboxes: false, enableClickSelection: true }}
              // the row classes (validation edge) were not redrawn while the editor was open
              onCellEditingStopped={(e) => e.api.redrawRows()}
              onSelectionChanged={(e) => setSelectedPath(e.api.getSelectedRows()[0]?.path ?? null)}
              rowClassRules={{
                "row-error": (p) =>
                  (diagnostics.get(p.data?.path ?? "") ?? []).some((d: { severity: string }) => d.severity === "error"),
                // a rule with nothing defined is drawn apart (its "ignored" warning is not a problem)
                "row-unfinished": (p) => (p.data ? isUnfinished(p.data.rule) : false),
                "row-warning": (p) =>
                  !(p.data && isUnfinished(p.data.rule)) &&
                  (diagnostics.get(p.data?.path ?? "") ?? []).some((d: { severity: string }) => d.severity === "warning"),
                "row-stale": (p) => developerMode && flags.get(p.data?.path ?? "")?.stale_override === true,
                "row-review": (p) => developerMode && (p.data ? reviewState(p.data.rule) === "review" : false),
                "row-validated": (p) => developerMode && (p.data ? reviewState(p.data.rule) === "validated" : false),
              }}
            />
            </div>
            {developerMode && selectedPath && selectedRule?.kind === "field" && (
              <OverridePane
                tree={tree}
                path={selectedPath}
                rule={selectedRule as FieldRule}
                target={targetPath(tree, selectedPath)}
                flag={flags.get(selectedPath)}
                onResolve={(op) => void reviewOp(op, selectedPath)}
                completer={(text, cursor) => gridContext.complete?.(selectedPath, "code", text, cursor) ?? Promise.resolve({ from: cursor, items: [] })}
                onCode={(code) =>
                  edit(
                    selectedPath,
                    (r) => {
                      if (r.kind === "field") r.transform.code_override = code;
                    },
                    `override:${selectedPath}`,
                  )
                }
                onClose={() => {
                  grid.current?.api.deselectAll();
                  setSelectedPath(null);
                }}
              />
            )}
            </>
          ) : tree || view === "project" ? null : (
            <div className="empty">{project ? "Pick a mapping" : "Open a project to begin"}</div>
          )}
        </main>
      </div>
      <div className="switches">
        <label>
          <input type="checkbox" checked={showIds} onChange={(e) => setShowIds(e.target.checked)} />
          Show rule ids
        </label>
        <label>
          <input
            type="checkbox"
            checked={developerMode}
            onChange={(e) => setDeveloperMode(e.target.checked)}
          />
          Developer mode
        </label>
      </div>
      {question && (
        <Confirm
          message={question.message}
          choices={question.choices}
          option={question.option}
          onChoose={(id, checked) => {
            question.resolve(id, checked);
            setQuestion(null);
          }}
        />
      )}
      {prompt && (
        <PromptDialog
          title={prompt.title}
          fields={prompt.fields}
          confirm={prompt.confirm}
          validate={prompt.validate}
          onDone={(values) => {
            prompt.resolve(values);
            setPrompt(null);
          }}
        />
      )}
      <footer>
        <div className="status">{status}</div>
        {(diagnostics.get("") ?? [])
          .filter((d) => view !== "paths" || !d.message.startsWith("paths:"))
          .map((d, i) => (
          <div key={`f${i}`} className={d.severity}>
            {d.severity}: {d.message}
          </div>
        ))}
        {report && (
          <div className={report.ok ? "report ok" : "report failed"}>
            {report.messages.map((m, i) => (
              <div key={`m${i}`}>{m}</div>
            ))}
            {report.diagnostics.map((d, i) => (
              <div key={`d${i}`} className={d.severity}>
                {d.severity}: {d.file ? `${d.file}: ` : ""}
                {d.rule ? `${d.rule}: ` : ""}
                {d.message}
              </div>
            ))}
          </div>
        )}
      </footer>
    </div>
  );
}
