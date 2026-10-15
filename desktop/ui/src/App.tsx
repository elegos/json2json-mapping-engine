import type { ColDef, ICellRendererParams, RowStyle, ValueSetterParams } from "ag-grid-community";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { AgGridReact } from "ag-grid-react";
import { type Choice, Confirm } from "./Confirm";
import { SharedConflict } from "./SharedConflict";
import { VersionControl } from "./VersionControl";
import { CompletingCellEditor, type GridContext } from "./CompletingCellEditor";
import { Lookups } from "./Lookups";
import { Paths } from "./Paths";
import { Validations } from "./Validations";
import { ProjectProperties } from "./ProjectProperties";
import { Golden } from "./Golden";
import { goldenDiagnostics } from "./goldenResult";
import { GoldenImport } from "./GoldenImport";
import { nameProblem } from "./mappings";
import { LocalSettings, type LocalState } from "./LocalSettings";
import { RunMenu } from "./RunMenu";
import { LoopOptions, type LoopOptionValues, loopOptionsSummary } from "./LoopOptions";
import { NewRuleDialog, type NewRuleValues } from "./NewRuleDialog";
import { PromptDialog, type PromptField } from "./PromptDialog";
import { RuleTip } from "./RuleTip";
import { OutputInputButton } from "./OutputInput";
import { RunReport } from "./RunReport";
import { dirName, inputDialogDir, mappedFilePath, outputCell, type OutputSource } from "./ruleOutput";

/** The folder the last input of a run was taken from (a convenience of this machine). */
/** How long a dropped rule stays lit (the `dropped` animation in styles.css). */
const DROP_FLASH_MS = 750;
const LAST_INPUT_DIR = "lastInputDir";
/** "1" when the user chose to always save the mapping before running it again on its input. */
const SAVE_BEFORE_RUN = "saveBeforeRun";
const localStorageGet = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};
const localStorageSet = (key: string, value: string): void => {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* kept only for convenience */
  }
};
import { AddMenu } from "./AddMenu";
import { SchemaStatusButtons } from "./SchemaStatus";
import {
  type ConfigIssue,
  type ConfigSchema,
  type ConfigValues,
} from "./projectConfig";
import { ProjectButton } from "./ProjectButton";
import { ImportView } from "./ImportView";
import { Wizard } from "./Wizard";
import { Guide } from "./Guide";
import { HelpMenu } from "./HelpMenu";
import { LicenseInfo } from "./LicenseInfo";
import { Tour } from "./Tour";
import { TOURS } from "./tourSteps";
import type { TourState } from "./tour";
import type { Book } from "./guideModel";
import { FunctionExplorer } from "./FunctionExplorer";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  changeStructure,
  checkTree,
  completeAt,
  configCheck,
  configRead,
  artifactsIgnore,
  artifactsState,
  artifactsTrack,
  engineStatus,
  vcsEnsureDriver,
  vcsInit,
  vcsState,
  engineUpgrade,
  configWrite,
  chooseProject,
  chooseSchemaFile,
  editTree,
  goldenCases,
  goldenCreate,
  goldenDelete,
  goldenImport,
  goldenRecord,
  goldenRun,
  inputFileGet,
  inputFileSet,
  publishDirGet,
  publishDirSet,
  buildDirGet,
  buildDirSet,
  syncedStatus,
  syncedRemoveGit,
  sharedPrepare,
  presenceAnnounce,
  type Editing,
  sharedSettle,
  sharedScan,
  sharedCopyMerge,
  sharedCopySettle,
  sharedCopyDiscard,
  type SharedAnswer,
  type VcsConflictItem,
  inputRun,
  chooseJsonFile,
  saveJsonFile,
  type GoldenResult,
  goldenRename,
  type GoldenCase,
  importSchema,
  mappingCreate,
  mappingDelete,
  mappingGolden,
  mappingRemoval,
  mappingRename,
  type SchemaKind,
  scaffoldRules,
  schemasList,
  schemasStatus,
  type SchemasStatus,
  initialProject,
  tourProjectCleanup,
  tourProjectPrepare,
  listFnFiles,
  type CommandReport,
  type PythonStatus,
  pythonStatus,
  readFn,
  reviewEdit,
  runMapper,
  sharedLookupShare,
  sharedLookupUnshare,
  writeFn,
} from "./api";
import {
  changedColumns,
  columnOf,
  childCount,
  descendants,
  moveRule,
  pathAfterMove,
  siblingOver,
  splitPath,
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
  validationsLabel,
  validationsOf,
  type ValidationsSection,
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

const WIZARD_KEY = "wizardAtStartup";

function wizardAtStartup(): boolean {
  try {
    return localStorage.getItem(WIZARD_KEY) !== "0";
  } catch {
    return true;
  }
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
  // the golden cases of the open mapping; `importingGolden` is the import dialog being open
  const [cases, setCases] = useState<GoldenCase[]>([]);
  const [importingGolden, setImportingGolden] = useState(false);
  /** The golden case editor holds changes not saved. */
  const [goldenDirty, setGoldenDirty] = useState(false);
  const goldenDirtyRef = useRef(false);
  /** The latest run of each golden case: the rules that failed are marked on the grid. */
  const [goldenRuns, setGoldenRuns] = useState<Record<string, GoldenResult>>({});
  goldenDirtyRef.current = goldenDirty;
  const [recent, setRecent] = useState<string[]>(loadRecent);
  const [wizard, setWizard] = useState(false);
  /** The project a document is being imported into (the import takes the whole screen). */
  const [importing, setImporting] = useState<string | null>(null);
  const [guide, setGuide] = useState<string | null>(null);
  const [explorer, setExplorer] = useState(false);
  const [license, setLicense] = useState(false);
  /** A project to show the properties of as soon as it is the open one (the wizard asked). */
  const [propertiesFor, setPropertiesFor] = useState<string | null>(null);
  const [tourRun, setTourRun] = useState<{ book: Book; index: number } | null>(null);
  /** The temporary copy of the tutorial project while a tour runs. */
  const [tourCopy, setTourCopy] = useState<string | null>(null);
  const beforeTour = useRef<{ project: string | null; developerMode: boolean; showIds: boolean } | null>(null);
  const [wizardStartup, setWizardStartup] = useState(wizardAtStartup);
  const grid = useRef<AgGridReact<Row>>(null);
  const [question, setQuestion] = useState<{
    message: string;
    choices: Choice[];
    option?: string;
    resolve: (id: string, checked: boolean) => void;
  } | null>(null);
  // shared-folder mode: this project is in a synced folder (set by `syncedGate`), and the merge
  // dialog waiting for the user's choices
  const [sharedMode, setSharedMode] = useState(false);
  const [conflict, setConflict] = useState<{
    file: string;
    other: string;
    kind: "rules" | "functions" | "text";
    items: VcsConflictItem[];
    resolve: (answer: { choices: Record<string, "mine" | "remote"> } | { whole: "mine" | "remote" } | null) => void;
  } | null>(null);
  const [prompt, setPrompt] = useState<{
    title: string;
    fields: PromptField[];
    confirm: string;
    validate: (values: Record<string, string>) => string | null;
    resolve: (values: Record<string, string> | null) => void;
  } | null>(null);
  // the user accepted to work on a project made with a newer engine (never persisted)
  const [olderAccepted, setOlderAccepted] = useState(false);
  const [versionControl, setVersionControl] = useState(false);
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
  const [lookupsVersion, setLookupsVersion] = useState(0);
  const [view, setView] = useState<"rules" | "lookups" | "paths" | "validations" | "golden" | "project">("rules");
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

  /** True when the golden case editor has nothing unsaved, or the user agrees to lose it. */
  const confirmGoldenLeave = useCallback(async (): Promise<boolean> => {
    if (!goldenDirtyRef.current) return true;
    const choice = await ask("The golden case has changes you have not saved. Discard them?", [
      { id: "discard", label: "Discard" },
      { id: "cancel", label: "Cancel", primary: true },
    ]);
    if (choice === "discard") setGoldenDirty(false);
    return choice === "discard";
  }, [ask]);

  /** True when it is fine to go on: nothing unsaved, or the user saved / chose to discard. */
  const guardUnsaved = useCallback(
    async (message: string, discardLabel: string): Promise<boolean> => {
      if (!dirtyRef.current) return confirmGoldenLeave();
      const choice = await ask(message, [
        { id: "save", label: "Save", primary: true },
        { id: "discard", label: discardLabel },
        { id: "cancel", label: "Cancel" },
      ]);
      if (choice === "save") return saveRef.current();
      return choice === "discard" && (await confirmGoldenLeave());
    },
    [ask, confirmGoldenLeave],
  );
  const guardRef = useRef(guardUnsaved);
  guardRef.current = guardUnsaved;

  // closing the window with unsaved changes
  useEffect(() => {
    const window = getCurrentWindow();
    const unlisten = window.onCloseRequested(async (event) => {
      if (!dirtyRef.current && !goldenDirtyRef.current) return;
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

  /** Compares the engine version the project declares with this tool's (mapper.toml): a newer tool
   * says it will update the project, an older one refuses unless the user accepts the risk, and
   * never moves the file back. `silent`: the tutorial's throwaway copy is updated without asking. */
  const engineGate = useCallback(
    async (dir: string, silent: boolean): Promise<{ open: boolean; older: boolean }> => {
      let found;
      try {
        found = await engineStatus(dir);
      } catch {
        return { open: true, older: false }; // not readable as a project: opening reports it
      }
      if (found.status === "current") return { open: true, older: false };
      if (found.status === "older") {
        let note = "";
        for (;;) {
          const { id, checked } = await askWithOption(
            `${note}This project was last opened with a newer version of the tool (engine ${found.project}); ` +
              `this one is ${found.tool}. It may not read the files, or generate them differently. ` +
              "mapper.toml is not changed.",
            [
              { id: "open", label: "Open anyway", primary: true },
              { id: "cancel", label: "Cancel" },
            ],
            "I understand the risk of incompatibility and want to open the project",
          );
          if (id !== "open") return { open: false, older: false };
          if (checked) return { open: true, older: true };
          note = "Tick the box to open it. ";
        }
      }
      if (!silent) {
        const was = found.project ? `with engine ${found.project}` : "with no engine version recorded";
        const id = await ask(
          `This project was last opened ${was}; this tool is ${found.tool}. Opening it updates the ` +
            `project to ${found.tool} (mapper.toml); regenerate its build files afterwards.`,
          [
            { id: "open", label: "Open and update", primary: true },
            { id: "cancel", label: "Cancel" },
          ],
        );
        if (id !== "open") return { open: false, older: false };
      }
      await engineUpgrade(dir);
      return { open: true, older: false };
    },
    [ask, askWithOption],
  );

  /** A project in a synced folder (OneDrive, SharePoint, ...). Two things, in this order:
   * a git repository there is not supported (the sync corrupts `.git`): the user deletes the `.git`
   * (the files stay, the history goes) or the project is not opened. Then nothing generated is
   * written in the folder: the user picks a local folder, per user and project (the app's config);
   * declining is allowed, nothing is built and this asks again. `force`: ask for the folder even
   * if chosen. Returns false when the project must not be opened. */
  const syncedGate = useCallback(
    async (dir: string, force = false): Promise<boolean> => {
      let found;
      try {
        found = await syncedStatus(dir);
      } catch {
        return true;
      }
      setSharedMode(Boolean(found.synced));
      if (!found.synced) {
        if (force) setStatus("This project is not in a synced folder: it builds in its own build/");
        return true;
      }
      if (found.git) {
        const id = await ask(
          `This project is a git repository in a ${found.synced} folder (${found.git}). The sync ` +
            "uploads and downloads the files of .git one by one and at different times, which corrupts " +
            "the repository: history that cannot be read, branches that disappear, commits that " +
            "cannot be pulled. It cannot be used that way.\n\n" +
            "Delete the .git folder? Your files stay exactly as they are now, so the current state " +
            "is not lost; the history (commits, branches) is. Keep the repository outside the " +
            "synced folder if you need it.\n\nIf you do not delete it, the project is not opened.",
          [
            { id: "delete", label: "Delete .git (lose the history)" },
            { id: "cancel", label: "Do not open the project", primary: true },
          ],
        );
        if (id !== "delete") return false;
        await syncedRemoveGit(dir);
        setStatus("The .git folder was deleted: the project is no longer a git repository");
      }
      if (!force && (await buildDirGet(dir))) return true;
      const id = await ask(
        `This project is in a ${found.synced} folder. Nothing generated is written there (the sync ` +
          "would upload the build, and everybody would overwrite everybody's). Choose a folder on " +
          "this machine to build in? Without one, build, check and publish stop, and this asks again " +
          "the next time.",
        [
          { id: "choose", label: "Choose a folder…", primary: true },
          { id: "ordinary", label: "This is not a synced folder" },
          { id: "later", label: "Not now" },
        ],
      );
      if (id === "choose") {
        const folder = await chooseProject(dir, "Local folder to build in");
        if (folder) {
          await buildDirSet(dir, folder);
          setStatus(`The build of this project goes to ${folder}`);
        }
      } else if (id === "ordinary") {
        await buildDirSet(dir, "-");
      }
      return true;
    },
    [ask],
  );

  /** A project outside a synced folder and outside any git repository: offer to put it under git.
   * Not binding: "Not now" asks again next time, "Never for this project" is remembered here. */
  const gitOffer = useCallback(
    async (dir: string) => {
      let refused: string[] = [];
      try {
        refused = JSON.parse(localStorage.getItem("noGitOffer") ?? "[]");
      } catch {
        /* nothing remembered */
      }
      if (refused.includes(dir)) return;
      let state;
      let synced;
      try {
        [state, synced] = await Promise.all([vcsState(dir), syncedStatus(dir)]);
      } catch {
        return;
      }
      if (!state.git || state.repo || synced.synced) return;
      const id = await ask(
        "This project is not under version control. Put it under git? That creates a repository here " +
          "(branch main, a .gitignore, and the tool's rule-level merge for mappings and functions) " +
          "and commits nothing; the Version control panel does that, after checking the project. " +
          "It is optional: the project works the same without.",
        [
          { id: "init", label: "Put it under git", primary: true },
          { id: "later", label: "Not now" },
          { id: "never", label: "Never for this project" },
        ],
      );
      if (id === "init") {
        await vcsInit(dir);
        setStatus("The project is under git: commit from Version control…");
      } else if (id === "never") {
        try {
          localStorage.setItem("noGitOffer", JSON.stringify([...refused, dir]));
        } catch {
          /* asked again next time */
        }
      }
    },
    [ask],
  );

  const openDir = useCallback(async (dir: string, remember = true) => {
    try {
      // first: a git repository kept in sync is not opened, and nothing may be written to it before
      if (remember && !(await syncedGate(dir))) return;
      const gate = await engineGate(dir, !remember);
      if (!gate.open) return;
      setOlderAccepted(gate.older);
      if (remember) await gitOffer(dir).catch((e) => setStatus(String(e instanceof Error ? e.message : e)));
      void vcsEnsureDriver(dir).catch(() => undefined); // best effort, and nobody's business
      const found = await listFnFiles(dir);
      setProject(dir);
      forgetHistory();
      setConfig(null);
      setConfigSchema(null);
      setCollapsed(new Set());
      // the tutorial project is a throwaway copy: it never joins the recent projects
      if (remember) {
        setRecent((old) => {
          const next = pushRecent(old, dir);
          try {
            localStorage.setItem("recentProjects", JSON.stringify(next));
          } catch {
            /* not persisted */
          }
          return next;
        });
      }
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
  }, [forgetHistory, engineGate, syncedGate, gitOffer]);

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

  /** The folder `Publish` writes to for this user: one of their own, or the project's setting. */
  const choosePublishDir = useCallback(async () => {
    if (!project) return;
    try {
      const mine = await publishDirGet(project);
      const choices: Choice[] = [{ id: "choose", label: "Choose a folder…", primary: true }];
      if (mine) choices.push({ id: "reset", label: "Use the project's setting" });
      choices.push({ id: "cancel", label: "Cancel" });
      const choice = await ask(
        mine
          ? `Publish writes to ${mine}, the folder you chose for this project on this machine. ` +
              "It beats the folder in the project's properties."
          : "Publish writes to the folder in the project's properties (Publish › dir), or to build/compiled " +
              "when it has none. Choose a folder of your own for this project on this machine?",
        choices,
      );
      if (choice === "choose") {
        const dir = await chooseProject(mine ?? project, "Folder to publish to");
        if (dir) {
          await publishDirSet(project, dir);
          setStatus(`Publish now writes to ${dir}`);
        }
      } else if (choice === "reset") {
        await publishDirSet(project, null);
        setStatus("Publish writes to the project's setting again");
      }
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, ask]);

  /** What Project properties shows of this machine and repository (see `LocalSettings`). */
  const [local, setLocal] = useState<LocalState>({ publishDir: null, buildDir: null, artifacts: null });
  const [localTick, setLocalTick] = useState(0);
  useEffect(() => {
    if (!project || view !== "project") return;
    let stale = false;
    void Promise.all([
      publishDirGet(project).catch(() => null),
      buildDirGet(project).catch(() => null),
      artifactsState(project).catch(() => null),
    ]).then(([publishDir, buildDir, artifacts]) => {
      if (!stale) setLocal({ publishDir, buildDir, artifacts });
    });
    return () => {
      stale = true;
    };
  }, [project, view, localTick]);

  /** Commit the generated files (build/compiled), or leave them to CI: .gitignore and the git index. */
  const chooseArtifacts = useCallback(async () => {
    if (!project) return;
    try {
      const found = await artifactsState(project);
      if (found.mode === "unknown") {
        await ask(
          "This project is not in a git repository (or git is not installed), so there is nothing to " +
            "commit or ignore.",
          [{ id: "ok", label: "OK", primary: true }],
        );
        return;
      }
      const committed = found.mode === "committed";
      const choice = await ask(
        committed
          ? `The generated files (build/compiled) are committed: ${found.tracked.length} in the repository. ` +
              "Stop committing them? They are added to .gitignore and removed from the repository (the " +
              "removal is staged, not committed; the files stay on your disk). Whoever deploys from the " +
              "repository then needs CI to build them."
          : "The generated files (build/compiled) are not committed: git ignores them and CI builds them. " +
              "Commit them again? They are taken out of .gitignore and staged.",
        [
          { id: "change", label: committed ? "Stop committing them" : "Commit them again", primary: true },
          { id: "cancel", label: "Cancel" },
        ],
      );
      if (choice !== "change") return;
      if (committed) {
        await artifactsIgnore(project);
        setStatus("build/compiled is ignored; commit .gitignore and the removal");
      } else {
        await artifactsTrack(project);
        setStatus("build/compiled is committed again; its files are staged");
      }
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, ask]);

  const openProject = useCallback(async () => {
    if (!(await switchGuard())) return;
    const dir = await chooseProject(recent[0]);
    if (dir) await openDir(dir);
  }, [openDir, recent, switchGuard]);

  useEffect(() => {
    initialProject().then(
      (dir) => {
        if (dir) void openDir(dir);
        else if (wizardAtStartup()) setWizard(true);
      },
      () => {},
    );
  }, [openDir]);

  const forgetRecent = useCallback((dir: string) => {
    setRecent((old) => {
      const next = old.filter((d) => d !== dir);
      try {
        localStorage.setItem("recentProjects", JSON.stringify(next));
      } catch {
        /* not persisted */
      }
      return next;
    });
  }, []);

  /** Shared-folder mode: before saving `mine` as `file`, the merge with what arrived in the folder
   * since this user saw it. The text or tree to save, "disk" (keep the one on disk: drop mine), or
   * null (the user cancelled). Outside a synced folder the answer is `mine` as it is. */
  const reconcile = useCallback(
    async (
      file: string,
      mine: { text: string } | { tree: FunctionalFile },
    ): Promise<{ text: string } | { tree: FunctionalFile } | "disk" | null> => {
      if (!project) return mine;
      const pick = (a: SharedAnswer) =>
        "tree" in mine ? { tree: a.tree as FunctionalFile } : { text: a.text as string };
      const prep = await sharedPrepare(project, file, mine);
      if (prep.state === "same") return mine;
      if (prep.state === "merged") {
        setStatus("Merged with the changes that arrived from the shared folder");
        return pick(prep);
      }
      const decision = await new Promise<
        { choices: Record<string, "mine" | "remote"> } | { whole: "mine" | "remote" } | null
      >((resolve) =>
        setConflict({
          file,
          other: "the shared folder",
          kind: prep.kind ?? "text",
          items: prep.items ?? [],
          resolve,
        }),
      );
      if (!decision) return null;
      if ("whole" in decision) return decision.whole === "mine" ? mine : "disk";
      return pick(await sharedSettle(project, file, mine, decision.choices));
    },
    [project],
  );

  const save = useCallback(async (): Promise<boolean> => {
    if (!project) return true;
    setBusy(true);
    try {
      let decayed: string[] = [];
      if (current && tree && fnDirty) {
        const answer = await reconcile(current, { tree });
        if (answer === null) {
          setStatus("not saved");
          return false;
        }
        if (answer === "disk") {
          await load(current, true);
          setStatus("Your changes were dropped: the version in the shared folder was kept");
          return true;
        }
        decayed = await writeFn(project, current, "tree" in answer ? answer.tree : tree);
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
  }, [project, current, tree, load, config, fnDirty, configDirty, reconcile]);
  saveRef.current = save;

  // Shared-folder mode: when the window comes back, look at what the sync brought. The open
  // mapping is read again if it changed and holds no unsaved edits (with edits, the merge happens
  // at save); a conflict copy is offered for merge into its original, once per session.
  // Presence: this tool says which mapping it has open every 30 s (a file of its own in the project,
  // `.j2jme/presence/`) and learns who else is editing. Advisory, nothing is locked.
  const [editing, setEditing] = useState<Editing[]>([]);
  const openMapping = current ? mappingName(current) : null;
  useEffect(() => {
    if (!project || !sharedMode) {
      setEditing([]);
      return;
    }
    let live = true;
    const beat = () =>
      presenceAnnounce(project, openMapping).then(
        (list) => live && setEditing(list),
        () => undefined, // nobody's business if the folder cannot be written
      );
    void beat();
    const timer = window.setInterval(() => void beat(), 30_000);
    window.addEventListener("focus", beat);
    return () => {
      live = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", beat);
    };
  }, [project, sharedMode, openMapping]);
  // leaving the project (or the tool) takes this tool's file away; a crash leaves it to expire
  useEffect(() => {
    if (!project || !sharedMode) return;
    return () => void presenceAnnounce(project, null).catch(() => undefined);
  }, [project, sharedMode]);

  const copiesDeclined = useRef(new Set<string>());
  const scanning = useRef(false);
  const fnDirtyRef = useRef(false);
  fnDirtyRef.current = fnDirty;
  useEffect(() => {
    if (!project || !sharedMode) return;
    const onFocus = async () => {
      if (scanning.current) return;
      scanning.current = true;
      try {
        const found = await sharedScan(project);
        if (current && found.changed.includes(current)) {
          if (fnDirtyRef.current) {
            setStatus("Changed in the shared folder: it is merged with your edits when you save");
          } else {
            await load(current, true);
            setStatus("Read again: it changed in the shared folder");
          }
        }
        for (const c of found.copies) {
          if (copiesDeclined.current.has(c.copy)) continue;
          if (fnDirtyRef.current && c.original === current) continue; // after the save
          const name = (p: string) => p.replace(/^.*\//, "");
          const id = await ask(
            `The sync made a conflict copy: ${name(c.copy)}, of ${name(c.original)}. Merge it into ` +
              "the original? The copy is removed afterwards.",
            [
              { id: "merge", label: "Merge it", primary: true },
              { id: "discard", label: "Delete the copy" },
              { id: "later", label: "Not now" },
            ],
          );
          if (id === "later") {
            copiesDeclined.current.add(c.copy);
            continue;
          }
          if (id === "discard") {
            await sharedCopyDiscard(project, c.copy);
          } else {
            let answer = await sharedCopyMerge(project, c.copy);
            if (answer.state === "conflict") {
              const decision = await new Promise<
                { choices: Record<string, "mine" | "remote"> } | { whole: "mine" | "remote" } | null
              >((resolve) =>
                setConflict({
                  file: name(c.original),
                  other: "the copy",
                  kind: answer.kind ?? "text",
                  items: answer.items ?? [],
                  resolve,
                }),
              );
              if (!decision || "whole" in decision) {
                copiesDeclined.current.add(c.copy);
                continue;
              }
              answer = await sharedCopySettle(project, c.copy, decision.choices);
            } else {
              answer = await sharedCopySettle(project, c.copy, {});
            }
            setStatus(`Merged ${name(c.copy)} into ${name(c.original)}`);
            if (current === c.original) await load(current, true);
          }
          await reloadFiles(null);
        }
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      } finally {
        scanning.current = false;
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [project, sharedMode, current, load, ask, reloadFiles]);

  /** Clearing / setting "Project wide" on a lookup: the files change, so the mapping is saved
   * first and read again. */
  const shareLookup = async (label: string) => {
    if (!project || !current) return;
    const stem = current.replace(/^.*\//, "").replace(/\.fn\.yaml$/, "");
    const choice = await ask(
      `Make @${label} a project-wide lookup? Its table moves out of ${stem} into lookups/${label}.lookup.yaml, and any mapping of the project can read it as @${label}. It is edited once, there.`,
      [
        { id: "share", label: "Make it project wide", primary: true },
        { id: "cancel", label: "Cancel" },
      ],
    );
    if (choice !== "share") return;
    if (!(await guardRef.current("Save the mapping before moving the lookup?", "Discard my changes"))) return;
    try {
      const clashing = await sharedLookupShare(project, stem, label);
      await load(current, true);
      setLookupsVersion((v) => v + 1);
      setStatus(
        `@${label} is project wide now` +
          (clashing.length ? `; ${clashing.join(", ")} still declare their own @${label}: remove it there` : ""),
      );
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  };
  const unshareLookup = async (label: string) => {
    if (!project || !current) return;
    const choice = await ask(
      `Stop @${label} being project wide? Every mapping that reads it gets its own copy of the table, and lookups/${label}.lookup.yaml is removed. Later changes to the table are then made in each mapping.`,
      [
        { id: "unshare", label: "Give each mapping a copy" },
        { id: "cancel", label: "Cancel", primary: true },
      ],
    );
    if (choice !== "unshare") return;
    if (!(await guardRef.current("Save the mapping before copying the lookup into the mappings?", "Discard my changes"))) return;
    try {
      const changed = await sharedLookupUnshare(project, label);
      await load(current, true);
      setLookupsVersion((v) => v + 1);
      setStatus(`@${label} copied into ${changed.length ? changed.join(", ") : "no mapping"}`);
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  };

  const run = useCallback(
    async (command: string) => {
      if (!project) return;
      // the commands read the files on disk, not what is in the grid
      if (!(await guardRef.current("Save before continuing?", "Continue without saving"))) return;
      setBusy(true);
      try {
        if (!(await syncedGate(project))) return; // no build folder chosen: ask again
        setReport(await runMapper(project, command, olderAccepted));
      } catch (e) {
        setStatus(String(e));
      } finally {
        setBusy(false);
      }
    },
    [project, olderAccepted, syncedGate],
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

  const editValidations = useCallback(
    (change: (section: ValidationsSection) => void) => {
      remember(treeRef.current, "validations");
      setTree((old) => {
        if (!old) return old;
        const copy = structuredClone(old);
        const section = validationsOf(copy);
        change(section);
        copy.validations = section;
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

  /** Puts the interface in the state a tour step needs, and waits for it to be drawn. */
  const applyTour = useCallback(
    async (state: TourState | undefined) => {
      if (!state) return;
      const frames = async (n = 3) => {
        for (let i = 0; i < n; i++) await new Promise((r) => requestAnimationFrame(r));
      };
      if (state.developerMode !== undefined) setDeveloperMode(state.developerMode);
      if (state.showIds !== undefined) setShowIds(state.showIds);
      if (state.explorer !== undefined) setExplorer(state.explorer);
      if (state.view === "project") await openProperties();
      else if (state.view) setView(state.view);
      setCollapsed(new Set());
      await frames();
      if (state.select !== undefined) {
        const api = grid.current?.api;
        const row = state.select
          ? flatten(treeRef.current?.rules ?? []).find((r) => r.rule.id === state.select)
          : undefined;
        if (!row || !api) {
          api?.deselectAll();
          setSelectedPath(null);
        } else {
          api.forEachNode((node) => {
            if (node.data?.path === row.path) {
              node.setSelected(true);
              api.ensureNodeVisible(node, "middle");
            }
          });
          setSelectedPath(row.path);
        }
        await frames();
      }
    },
    [openProperties, setDeveloperMode, setShowIds],
  );
  const applyTourRef = useRef(applyTour);
  applyTourRef.current = applyTour;

  const startTour = useCallback(
    async (book: Book) => {
      if (tourRun || !(await switchGuard())) return;
      setGuide(null);
      setWizard(false);
      try {
        const copy = await tourProjectPrepare();
        beforeTour.current = { project, developerMode, showIds };
        setTourCopy(copy);
        await openDir(copy, false);
        setTourRun({ book, index: 0 });
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [tourRun, switchGuard, project, developerMode, showIds, openDir],
  );

  const endTour = useCallback(async () => {
    const before = beforeTour.current;
    const copy = tourCopy;
    setTourRun(null);
    setExplorer(false);
    if (before) {
      setDeveloperMode(before.developerMode);
      setShowIds(before.showIds);
    }
    if (before?.project) {
      await openDir(before.project);
    } else {
      setProject(null);
      setFiles([]);
      setCurrent(null);
      setTree(null);
      setReport(null);
      setStatus("");
    }
    setTourCopy(null);
    beforeTour.current = null;
    if (copy) await tourProjectCleanup(copy).catch(() => {});
  }, [tourCopy, openDir, setDeveloperMode, setShowIds]);

  // the first time a project is open, and the first time Developer mode is on, a tour is offered
  const offered = useRef(false);
  useEffect(() => {
    if (!project || tourCopy || tourRun || wizard || offered.current) return;
    const key = developerMode ? "tourOffered.developer" : "tourOffered.functional";
    let seen = true;
    try {
      seen = localStorage.getItem(key) === "1";
    } catch {
      /* not remembered: do not nag */
    }
    if (seen) return;
    offered.current = true;
    try {
      localStorage.setItem(key, "1");
    } catch {
      /* not persisted */
    }
    void (async () => {
      const choice = await ask(
        developerMode
          ? "Take a quick tour of the developer features? It runs on a sample project and keeps nothing."
          : "Take a quick tour of the tool? It runs on a sample project and keeps nothing; the ? button offers it again.",
        [
          { id: "tour", label: "Take the tour", primary: true },
          { id: "no", label: "Not now" },
        ],
      );
      offered.current = false;
      if (choice === "tour") void startTour(developerMode ? "developer" : "functional");
    })();
  }, [project, developerMode, tourCopy, tourRun, wizard, ask, startTour]);

  useEffect(() => {
    if (propertiesFor && propertiesFor === project) {
      setPropertiesFor(null);
      void openProperties();
    }
  }, [propertiesFor, project, openProperties]);

  const selectedRow = () => grid.current?.api?.getSelectedRows()[0];

  const [newRule, setNewRule] = useState<{ kind: string; at: { parent: string | null; index: number | null } } | null>(null);
  /** The loop whose advanced options are open (its row path). */
  const [loopOptions, setLoopOptions] = useState<string | null>(null);

  /** Adds the rule; the reason it was refused, or null once added. */
  const insertRule = useCallback(
    async (kind: string, at: { parent: string | null; index: number | null }, values: NewRuleValues = {}): Promise<string | null> => {
      const current = treeRef.current;
      if (!current) return null;
      try {
        const next = await changeStructure(current, { op: "add_rule", ...at, kind, ...values });
        remember(current);
        setTree(next);
        if (at.parent) setCollapsed((old) => new Set([...old].filter((p) => p !== at.parent)));
        setStatus("");
        // bring the new rule into view once the grid has it
        const index = at.index ?? childCount(current, at.parent);
        const added = `${at.parent ? `${at.parent}.` : ""}rules[${index}]`;
        setTimeout(() => {
          const node = grid.current?.api?.getRowNode(added);
          if (node) grid.current?.api.ensureNodeVisible(node, "bottom");
        }, 60);
        return null;
      } catch (e) {
        return String(e instanceof Error ? e.message : e);
      }
    },
    [remember],
  );

  /** A field, object or loop asks its name (and, for a field, type and Req.) in a dialog first;
   *  a lookup is added at once. */
  const addRule = useCallback(
    (kind: string, atRoot = false) => {
      if (!treeRef.current) return;
      const at = atRoot ? { parent: null, index: null } : insertionPoint(selectedRow());
      if (kind === "lookup") void insertRule(kind, at).then((error) => error && setStatus(error));
      else setNewRule({ kind, at });
    },
    [insertRule],
  );

  /** The rule that has just been dropped (its path) and when its highlight began. */
  const dropped = useRef<{ path: string; at: number } | null>(null);

  /** Opens a one-row gap where a dragged rule would land: the rows from there on slide down (the
   *  CSS `translate`, which ag-grid's own `transform` positioning leaves alone). Null closes it. */
  const markDrop = useCallback((sibling: string | null, after = false, dragged: string | null = null) => {
    const api = grid.current?.api;
    document.querySelectorAll<HTMLElement>(".grid .ag-row").forEach((el) => {
      el.style.translate = "";
      el.classList.remove("drag-source");
    });
    if (!api || sibling === null) return;
    const first = api.getRowNode(sibling);
    if (!first || first.rowIndex === null) return;
    let from = first.rowIndex;
    const height = first.rowHeight ?? 42;
    if (after) {
      // behind the sibling and everything inside it
      from += 1;
      for (let i = from; i < api.getDisplayedRowCount(); i++) {
        const path = api.getDisplayedRowAtIndex(i)?.data?.path as string | undefined;
        if (!path?.startsWith(`${sibling}.rules[`)) break;
        from = i + 1;
      }
    }
    document.querySelectorAll<HTMLElement>(".grid .ag-row[row-index]").forEach((el) => {
      if (Number(el.getAttribute("row-index")) >= from) el.style.translate = `0 ${height}px`;
      if (dragged !== null && el.getAttribute("row-id") === dragged) el.classList.add("drag-source");
    });
  }, []);

  /** The sibling the pointer is over while a rule is dragged, and whether it lands behind it. */
  const dropTarget = (e: { node: { data?: Row }; overNode?: { data?: Row } | null }) => {
    const dragged = e.node.data?.path;
    const over = e.overNode?.data?.path;
    if (!dragged || !over) return null;
    const sibling = siblingOver(dragged, over);
    if (!sibling || sibling === dragged) return null;
    return { dragged, sibling, after: splitPath(sibling).index > splitPath(dragged).index };
  };

  const dropRule = useCallback(
    (found: { dragged: string; sibling: string; after: boolean } | null, overSomething: boolean) => {
      const current = treeRef.current;
      if (!current) return;
      if (!found) {
        if (overSomething) setStatus("A rule moves only among the rules of its own level (the root, an object or a loop).");
        return;
      }
      const moved = moveRule(current, found.dragged, found.sibling, found.after);
      if (!moved) return;
      const { parent, index: from } = splitPath(found.dragged);
      remember(current);
      setTree(moved.tree);
      setCollapsed((old) => new Set([...old].map((p) => pathAfterMove(p, parent, from, moved.index))));
      setStatus("");
      // the rule that landed lights up for a moment. Kept in a ref and given to the row by its class
      // and style (not by touching the element), so that a row the grid draws again meanwhile goes on
      // from where the animation was instead of losing it
      const landed = `${parent ? `${parent}.` : ""}rules[${moved.index}]`;
      dropped.current = { path: landed, at: Date.now() + 80 };
      setTimeout(() => {
        const node = grid.current?.api?.getRowNode(landed);
        if (node) grid.current?.api.redrawRows({ rowNodes: [node] });
      }, 80);
      setTimeout(() => {
        dropped.current = null;
      }, DROP_FLASH_MS + 400);
    },
    [remember],
  );

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

  // the schema files can change outside the tool while the mapping is open: when the window is
  // back in focus the status and the check are read again (nothing is moved to review by itself)
  useEffect(() => {
    if (!project || !current) return;
    const again = () => setSchemaTick((n) => n + 1);
    window.addEventListener("focus", again);
    return () => window.removeEventListener("focus", again);
  }, [project, current]);

  const loadCases = useCallback(async () => {
    if (!project || !current) {
      setCases([]);
      return;
    }
    try {
      setCases(await goldenCases(project, mappingName(current)));
    } catch (e) {
      setCases([]);
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, current]);
  useEffect(() => {
    void loadCases();
  }, [view, loadCases]);

  // the Output column: what the rules give on a golden case or on any JSON file
  const [outputSource, setOutputSource] = useState<OutputSource | null>(null);
  const [outputResult, setOutputResult] = useState<GoldenResult | null>(null);
  const [outputFileMissing, setOutputFileMissing] = useState(false);
  const [rememberedFile, setRememberedFile] = useState<string | null>(null);
  // the input the user just chose: if it cannot be read they are told in an alert, not in the status line
  const alertForInput = useRef<string | null>(null);
  // bumped to run the mapping again on the same input
  const [runRev, setRunRev] = useState(0);
  useEffect(() => {
    // the file used last time on this mapping (kept outside the project)
    setOutputSource(null);
    setOutputResult(null);
    setRememberedFile(null);
    if (!project || !current) return;
    let stale = false;
    inputFileGet(project, mappingName(current)).then(
      (file) => {
        if (stale || !file) return;
        setRememberedFile(file);
        setOutputSource({ kind: "file", path: file });
      },
      () => undefined,
    );
    return () => {
      stale = true;
    };
  }, [project, current]);
  // the run is on the saved file: a save, another mapping or another input runs it again
  const outputKey = JSON.stringify(outputSource);
  // a saved function changes what the mapping gives
  const [functionsRev, setFunctionsRev] = useState(0);
  useEffect(() => {
    setOutputFileMissing(false);
    if (!project || !current || !outputSource) {
      setOutputResult(null);
      return;
    }
    let stale = false;
    const mapping = mappingName(current);
    const run =
      outputSource.kind === "case"
        ? goldenRun(project, mapping, [outputSource.name]).then((got) => got[0] ?? null)
        : inputRun(project, mapping, outputSource.path);
    run.then(
      (result) => !stale && setOutputResult(result),
      (e) => {
        if (stale) return;
        setOutputResult(null);
        if (outputSource.kind === "file") setOutputFileMissing(true);
        const message = String(e instanceof Error ? e.message : e);
        setStatus(message);
        if (outputSource.kind === "file" && alertForInput.current === outputKey) {
          alertForInput.current = null;
          void ask(`The file ${outputSource.path} cannot be read as an input:\n\n${message}`, [
            { id: "ok", label: "OK", primary: true },
          ]);
        }
      },
    );
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, current, saved, outputKey, functionsRev, runRev]);
  const pickOutputFile = useCallback(async () => {
    const lastDir = localStorageGet(LAST_INPUT_DIR);
    const file = await chooseJsonFile("Input to run the mapping on", inputDialogDir(rememberedFile, lastDir, project));
    if (!file || !project || !current) return;
    localStorageSet(LAST_INPUT_DIR, dirName(file));
    setRememberedFile(file);
    alertForInput.current = JSON.stringify({ kind: "file", path: file });
    setOutputSource({ kind: "file", path: file });
    await inputFileSet(project, mappingName(current), file).catch(() => undefined);
  }, [project, current, rememberedFile]);

  /** Runs the mapping again on the input. The run is on the saved file, so a mapping with changes
   * is saved first; the question is asked once if the user ticks "Remember this decision". */
  const refreshOutput = useCallback(async () => {
    if (fnDirtyRef.current) {
      if (localStorageGet(SAVE_BEFORE_RUN) !== "1") {
        const { id, checked } = await askWithOption(
          "The mapping has changes not saved, and the run uses the saved file.",
          [
            { id: "save", label: "Save and run", primary: true },
            { id: "cancel", label: "Cancel" },
          ],
          "Remember this decision",
        );
        if (id !== "save") return;
        if (checked) localStorageSet(SAVE_BEFORE_RUN, "1");
      }
      // a save runs the mapping again by itself
      await saveRef.current();
      return;
    }
    setRunRev((n) => n + 1);
  }, [askWithOption]);

  /** Takes the grid to a rule and selects its Source: unfolds what hides it, drops a filter that
   * does, scrolls to it. */
  const showRule = useCallback(
    async (path: string) => {
      setCollapsed((old) => new Set([...old].filter((p) => !path.startsWith(`${p}.rules[`))));
      setFilterText("");
      setStateFilter("all");
      for (let i = 0; i < 4; i++) await new Promise((r) => requestAnimationFrame(r));
      const api = grid.current?.api;
      const node = api?.getRowNode(path);
      if (!api || !node) return;
      node.setSelected(true);
      api.ensureNodeVisible(node, "middle");
      if (node.rowIndex !== null) api.setFocusedCell(node.rowIndex, "source");
    },
    [],
  );

  const downloadMapped = useCallback(async () => {
    if (!outputSource || !outputResult) return;
    try {
      const file = await saveJsonFile("Save the mapped JSON", mappedFilePath(outputSource, project), outputResult.output);
      if (file) setStatus(`Mapped JSON saved to ${file}`);
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [outputSource, outputResult, project]);

  const importCase = useCallback(
    async (v: { name: string; input: string; expected: string | null; errors: string | null }) => {
      if (!project || !current) return "No mapping is open.";
      try {
        await goldenImport(project, mappingName(current), v.name, {
          input: v.input,
          expected: v.expected,
          errors: v.errors,
        });
        setImportingGolden(false);
        await loadCases();
        return null;
      } catch (e) {
        return String(e instanceof Error ? e.message : e);
      }
    },
    [project, current, loadCases],
  );

  const newCase = useCallback(async () => {
    if (!project || !current) return;
    const taken = cases.map((c) => c.name);
    const got = await askValues(
      "New golden case",
      [{ key: "name", label: "Case name", value: "", hint: "It starts with an empty input, {}: fill it in the editor." }],
      "Create",
      (v) =>
        /^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(v.name.trim())
          ? taken.includes(v.name.trim())
            ? `There is already a case called ${v.name.trim()}.`
            : null
          : "Letters, digits, _ and -.",
    );
    if (!got) return;
    try {
      await goldenCreate(project, mappingName(current), got.name.trim());
      await loadCases();
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, current, cases, askValues, loadCases]);

  /** Runs golden cases of the open mapping; the saved file is what runs, so unsaved changes are
   * saved first (or the run is given up). */
  // the marks are of the file as it was run: another file, or a saved change, makes them stale
  useEffect(() => {
    setGoldenRuns({});
  }, [saved, current]);

  const runGolden = useCallback(
    async (names: string[] | null): Promise<GoldenResult[] | null> => {
      if (!project || !current) return null;
      if (fnDirtyRef.current) {
        const choice = await ask("The mapping has changes not saved, and the cases run on the saved file.", [
          { id: "save", label: "Save and run", primary: true },
          { id: "cancel", label: "Cancel" },
        ]);
        if (choice !== "save" || !(await saveRef.current())) return null;
      }
      try {
        const got = await goldenRun(project, mappingName(current), names ?? undefined);
        setGoldenRuns((old) => ({ ...old, ...Object.fromEntries(got.map((r) => [r.name, r])) }));
        return got;
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
        return null;
      }
    },
    [project, current, ask],
  );

  const recordGolden = useCallback(
    async (name: string): Promise<boolean> => {
      if (!project || !current) return false;
      const choice = await ask(
        `Make what the mapping gives now the expected result of ${name}? ` +
          "Its expected output, and its expected errors, are replaced by this output and the rules that failed.",
        [
          { id: "record", label: "Record", primary: true },
          { id: "cancel", label: "Cancel" },
        ],
      );
      if (choice !== "record") return false;
      try {
        await goldenRecord(project, mappingName(current), name);
        return true;
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
        return false;
      }
    },
    [project, current, ask],
  );

  const renameCase = useCallback(
    async (name: string) => {
      if (!project || !current || !(await confirmGoldenLeave())) return;
      const others = cases.map((c) => c.name).filter((n) => n !== name);
      const got = await askValues(
        "Rename golden case",
        [{ key: "name", label: "Case name", value: name }],
        "Rename",
        (v) =>
          /^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(v.name.trim())
            ? others.includes(v.name.trim())
              ? `There is already a case called ${v.name.trim()}.`
              : null
            : "Letters, digits, _ and -.",
      );
      if (!got || got.name.trim() === name) return;
      try {
        await goldenRename(project, mappingName(current), name, got.name.trim());
        await loadCases();
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [project, current, cases, askValues, loadCases, confirmGoldenLeave],
  );

  const deleteCase = useCallback(
    async (name: string) => {
      if (!project || !current || !(await confirmGoldenLeave())) return;
      const mapping = mappingName(current);
      const choice = await ask(
        `Delete the golden case '${name}' of ${mapping}? Its input, expected output and expected errors files are removed.`,
        [
          { id: "delete", label: "Delete" },
          { id: "cancel", label: "Cancel", primary: true },
        ],
      );
      if (choice !== "delete") return;
      try {
        await goldenDelete(project, mapping, name);
        await loadCases();
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [project, current, ask, loadCases],
  );

  /** Offers the empty rules the output schema describes and the mapping lacks (it adds only the
   * missing ones). After a load nothing to add is silent; asked for, it says so. */
  const offerScaffold = useCallback(
    async (from: FunctionalFile, asked: boolean) => {
      if (!project || !current) return;
      const stem = mappingName(current);
      const found = await scaffoldRules(from, project, stem, false);
      const left =
        found.skipped.length > 0
          ? ` ${found.skipped.length} cannot be laid out (${found.skipped.slice(0, 3).join("; ")}${found.skipped.length > 3 ? "; …" : ""}).`
          : "";
      if (found.added === 0) {
        if (asked) setStatus(`Every property the output schema describes already has a rule.${left}`);
        return;
      }
      const choice = await ask(
        `Create ${found.added} empty rule${found.added === 1 ? "" : "s"} from the output schema? ` +
          `They are ignored until a Source is defined.${left}`,
        [
          { id: "create", label: "Create the rules", primary: true },
          { id: "no", label: "Not now" },
        ],
      );
      if (choice !== "create") return;
      const made = await scaffoldRules(from, project, stem, true);
      if (made.tree) {
        remember(from, "scaffold");
        setTree(made.tree);
      }
    },
    [project, current, remember, ask],
  );

  /** Loads (or replaces) the input / output schema: the file is copied into the project under the
   * mapping's name, so the mapping reads the copy; a `schemas:` override in the file would hide
   * it, so it is dropped (the file is then unsaved, as for any edit). */
  const pickSchema = useCallback(
    async (kind: SchemaKind, own?: string) => {
      const open = treeRef.current;
      if (!open || !project || !current) return;
      try {
        // `own`: one of the project's schemas, by its path from the root; else a file is picked
        const source = own ?? (await chooseSchemaFile(kind, project));
        if (!source) return;
        const there = schemas?.[kind];
        if (there?.state === "ok") {
          const choice = await ask(
            `Replace the ${kind} schema (${there.path}) with ${own ?? source}? ` +
              "The validated rules it no longer fits go back to review.",
            [
              { id: "replace", label: "Replace it", primary: true },
              { id: "no", label: "Cancel" },
            ],
          );
          if (choice !== "replace") return;
        }
        const stem = mappingName(current);
        const loaded = await importSchema(project, stem, kind, source, open);
        const moved = loaded.moved?.length ?? 0;
        let next = loaded.tree ?? open;
        if (open.schemas[kind] || moved > 0) {
          remember(open, "schemas");
          next = { ...next, schemas: { ...next.schemas, [kind]: null } };
          setTree(next);
        }
        setSchemaTick((n) => n + 1);
        setStatus(
          moved > 0
            ? `${moved} validated rule${moved === 1 ? "" : "s"} went back to review: the ${kind} schema no longer fits ${moved === 1 ? "it" : "them"}.`
            : "",
        );
        // a new output schema: offer the rules it describes, empty, for the user to fill in
        if (kind === "output") await offerScaffold(next, false);
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [project, current, remember, ask, schemas, offerScaffold],
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
        [
          ...live,
          ...(current && report ? report.diagnostics : []),
          ...(current ? goldenDiagnostics(Object.values(goldenRuns), current) : []),
        ],
        current ?? "",
      ),
    [current, report, live, goldenRuns],
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
        colId: "drag",
        width: 34,
        pinned: "left",
        sortable: false,
        suppressMovable: true,
        resizable: false,
        rowDrag: (p) => p.data !== undefined,
        rowDragText: (p) => (p.rowNode?.data ? nameOf(p.rowNode.data.rule) : ""),
        cellClass: "drag-cell",
        valueGetter: () => "",
        tooltipValueGetter: () => "Drag to reorder among the rules of the same level",
      },
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
      {
        headerName: "Kind",
        colId: "kind",
        valueGetter: (p) => p.data?.rule.kind,
        width: 96,
        // a loop has options beyond its Source, Filter and Output: the icon beside it opens them
        cellRenderer: (p: ICellRendererParams<Row>) => {
          const rule = p.data?.rule;
          if (rule?.kind !== "loop") return p.value;
          const summary = loopOptionsSummary(rule as unknown as Record<string, unknown>);
          return (
            <span>
              loop{" "}
              <button
                className={summary ? "link loop-options-button set" : "link loop-options-button"}
                title={summary ? `Loop options: ${summary}` : "Loop options (order, numbering, when empty…)"}
                aria-label="Loop options"
                onClick={(e) => {
                  e.stopPropagation();
                  setLoopOptions(p.data!.path);
                }}
              >
                ⚙
              </button>
            </span>
          );
        },
      },
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
        headerName: "Output",
        colId: "output",
        width: 200,
        valueGetter: (p) => (p.data ? (outputCell(outputResult, p.data.path)?.text ?? "") : ""),
        // nothing chosen yet: the first row says what the column is for
        cellRenderer: (p: ICellRendererParams<Row>) =>
          !outputSource && p.node.rowIndex === 0 ? <span className="muted">Select an output file…</span> : p.value,
        cellClass: (p) => `output-cell ${p.data ? (outputCell(outputResult, p.data.path)?.state ?? "") : ""}`,
        tooltipValueGetter: (p) => (p.data ? (outputCell(outputResult, p.data.path)?.tooltip ?? "") : ""),
      },
      {
        headerName: "Description",
        colId: "description",
        width: 260,
        editable: true,
        valueGetter: (p) => p.data?.rule.description ?? "",
        // long, often several lines: edited in a text area (Shift+Enter breaks a line) and read in
        // full in a bubble that scrolls
        cellEditor: "agLargeTextCellEditor",
        cellEditorPopup: true,
        cellEditorParams: { rows: 6, cols: 60, maxLength: 4000 },
        tooltipComponent: RuleTip,
        tooltipValueGetter: (p) => String(p.value ?? ""),
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
        // long, often several lines: edited in a text area (Shift+Enter breaks a line) and read in
        // full in a bubble that scrolls
        cellEditor: "agLargeTextCellEditor",
        cellEditorPopup: true,
        cellEditorParams: { rows: 6, cols: 60, maxLength: 4000 },
        tooltipComponent: RuleTip,
        tooltipValueGetter: (p) => String(p.value ?? ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.validation.notes = String(p.newValue ?? "") || null;
          });
          return true;
        },
      },
    ];
  }, [edit, remoteEdit, showIds, developerMode, diagnostics, flags, invalidColumns, collapsed, toggleFold, outputSource, outputResult]);

  return (
    <div className="app">
      <header>
        <ProjectButton recent={recent} onOpen={openProject} onPick={async (d) => {
            if (await switchGuard()) await openDir(d);
          }} />
        <button title="Start: recent projects, new project" aria-label="Start wizard" onClick={() => setWizard(true)}>
          🧙‍♂️
        </button>
        <MiddleEllipsis className="project" text={project ?? "no project"} />
        <button className="history" title="Undo (Ctrl + Z)" disabled={!canUndo || busy} onClick={undo}>
          ↶
        </button>
        <button className="history" title="Redo (Ctrl + Y)" disabled={!canRedo || busy} onClick={redo}>
          ↷
        </button>
        <span className="commands" data-tour="actions">
          <button disabled={!dirty || busy} onClick={() => void save()}>
            Save{dirty ? " ●" : ""}
          </button>
          <button
            disabled={!project || busy}
            title="Commit, pull and push (git): checks and builds before committing"
            onClick={() => setVersionControl(true)}
          >
            Version control…
          </button>
          {/* transpile, build and publish are the developer's: a functional user only checks */}
          <RunMenu
            disabled={!canBuild}
            steps={
              developerMode
                ? [
                    { id: "transpile", label: "Transpile", title: "Rule tree to .map.py files" },
                    { id: "build", label: "Build", title: "Transpile and compile into build/compiled" },
                    { id: "check", label: "Check…", title: "Regenerate and compare with the committed files" },
                    { id: "publish", label: "Publish", title: "Check and build, then write the files and manifest.json to the publish folder" },
                  ]
                : []
            }
            onRun={(c) => run(c)}
          />
        </span>
        <HelpMenu
          onGuide={() => setGuide("functional")}
          onExplorer={() => setExplorer((on) => !on)}
          onTour={(book) => void startTour(book)}
          onLicense={() => setLicense(true)}
        />
      </header>
      {license && <LicenseInfo onClose={() => setLicense(false)} />}
      {tourCopy && (
        <div className="banner">Tutorial project: read-only, nothing here is kept.</div>
      )}
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
              <button
                className={view === "validations" ? "tab active" : "tab"}
                onClick={() => setView("validations")}
              >
                {tree ? validationsLabel(tree) : "Validations"}
              </button>
              <button className={view === "golden" ? "tab active" : "tab"} onClick={() => setView("golden")}>
                Golden{goldenDirty ? " ●" : ""}
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
            >
              {developerMode && (
                <LocalSettings
                  state={local}
                  synced={sharedMode}
                  onPublishDir={() => void choosePublishDir().then(() => setLocalTick((t) => t + 1))}
                  onBuildDir={() =>
                    project && void syncedGate(project, true).catch((e) => setStatus(String(e))).then(() => setLocalTick((t) => t + 1))
                  }
                  onArtifacts={() => void chooseArtifacts().then(() => setLocalTick((t) => t + 1))}
                />
              )}
            </ProjectProperties>
          )}
          {/* kept while the mapping is open, so a draft survives a visit to another view */}
          {tree && current && (
            <div style={view === "golden" ? undefined : { display: "none" }}>
              <Golden
                key={`${project}|${current}`}
                project={project ?? ""}
                mapping={mappingName(current)}
                cases={cases}
                onImport={() => setImportingGolden(true)}
                onNew={() => void newCase()}
                onDirty={setGoldenDirty}
                onSaved={() => void loadCases()}
                onRun={runGolden}
                onRecord={recordGolden}
                confirmLeave={confirmGoldenLeave}
                onRename={(name) => void renameCase(name)}
                onDelete={(name) => void deleteCase(name)}
              />
            </div>
          )}
          {tree && view === "paths" && (
            <Paths
              paths={tree.paths}
              issues={(diagnostics.get("") ?? []).filter((d) => d.message.startsWith("paths:"))}
              onChange={editPaths}
            />
          )}
          {tree && view === "validations" && (
            <Validations
              validations={validationsOf(tree)}
              diagnostics={diagnostics}
              onChange={editValidations}
              complete={(path, text, cursor) =>
                gridContext.complete?.(path, "expect", text, cursor) ?? Promise.resolve({ from: cursor, items: [] })
              }
            />
          )}
          {tree && project && view === "lookups" && (
            <Lookups
              tree={tree}
              project={project}
              version={lookupsVersion}
              beforeDiskChange={() =>
                guardRef.current(
                  "The project's lookups change files the open mapping is read from, and it is read again afterwards. Save it first?",
                  "Discard my changes",
                )
              }
              afterDiskChange={async (message) => {
                if (current) await load(current, true);
                setLookupsVersion((v) => v + 1);
                setStatus(message);
              }}
              onShare={(label) => void shareLookup(label)}
              onUnshare={(label) => void unshareLookup(label)}
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
              onAdd={() => addRule("lookup", true)}
              onDelete={(path) => void deleteRule(path)}
            />
          )}
          {tree && view === "rules" && (
            <div className="toolbar">
              <AddMenu onAdd={(kind) => addRule(kind)} />
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
              <SchemaStatusButtons
                status={schemas}
                onPick={(kind) => void pickSchema(kind)}
                onUse={(kind, file) => void pickSchema(kind, file)}
                listFiles={() => schemasList(project ?? "")}
                onScaffold={() => {
                  const open = treeRef.current;
                  if (open) offerScaffold(open, true).catch((e) => setStatus(String(e instanceof Error ? e.message : e)));
                }}
              >
                <OutputInputButton
                  cases={cases}
                  source={outputSource}
                  fileMissing={outputFileMissing}
                  rememberedFile={rememberedFile}
                  onRefresh={() => void refreshOutput()}
                  onPick={(next) => {
                    if (next?.kind === "file") alertForInput.current = JSON.stringify(next);
                    setOutputSource(next);
                    // a file is remembered for next time; "No output" forgets it
                    if (project && current && next?.kind !== "case") {
                      void inputFileSet(project, mappingName(current), next?.path ?? null).catch(() => undefined);
                    }
                  }}
                  onChooseFile={() => void pickOutputFile()}
                />
                <RunReport result={outputResult} onDownload={() => void downloadMapped()} onShowRule={(path) => void showRule(path)} />
              </SchemaStatusButtons>
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
              tooltipInteraction
              onRowDragMove={(e) => {
                const found = dropTarget(e);
                markDrop(found?.sibling ?? null, found?.after, found?.dragged ?? null);
              }}
              onRowDragLeave={() => markDrop(null)}
              onRowDragCancel={() => markDrop(null)}
              onRowDragEnd={(e) => {
                markDrop(null);
                dropRule(dropTarget(e), !!e.overNode?.data);
              }}
              tooltipHideDelay={600000}
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
              getRowStyle={(p) =>
                dropped.current && p.data?.path === dropped.current.path
                  ? ({ "--drop-elapsed": `${Math.min(0, dropped.current.at - Date.now())}ms` } as RowStyle)
                  : undefined
              }
              rowClassRules={{
                "just-dropped": (p) => dropped.current !== null && p.data?.path === dropped.current.path,
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
        <FunctionExplorer
          project={project}
          open={explorer}
          onSaved={() => setFunctionsRev((v) => v + 1)}
          reconcile={async (file, text) => {
            const answer = await reconcile(`fn/${file}.fn`, { text });
            return answer === null || answer === "disk" ? answer : "text" in answer ? answer.text : text;
          }}
          beforeDiskChange={() =>
            guardRef.current(
              "Renaming a function changes files the open mapping is read from, and it is read again afterwards. Save it first?",
              "Discard my changes",
            )
          }
          afterDiskChange={async (message) => {
            if (current) await load(current, true);
            setStatus(message);
          }}
          onClose={() => setExplorer(false)}
        />
        <div className="side-rail" role="tablist" aria-label="Side panels">
          <button
            role="tab"
            aria-selected={explorer}
            className={explorer ? "active" : undefined}
            title="Functions: the built-ins and the project's own, and their editor"
            onClick={() => setExplorer((on) => !on)}
          >
            fn
          </button>
        </div>
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
      {wizard && (
        <Wizard
          onHelp={() => setGuide("functional")}
          recent={recent}
          showAtStartup={wizardStartup}
          onShowAtStartup={(value) => {
            setWizardStartup(value);
            try {
              localStorage.setItem(WIZARD_KEY, value ? "1" : "0");
            } catch {
              /* not persisted */
            }
          }}
          onOpenDialog={async () => {
            if (!(await switchGuard())) return;
            const dir = await chooseProject(recent[0]);
            if (!dir) return;
            setWizard(false);
            await openDir(dir);
          }}
          onOpenRecent={async (dir) => {
            if (!(await switchGuard())) return;
            setWizard(false);
            await openDir(dir);
          }}
          onForget={forgetRecent}
          onCreated={async (dir, properties) => {
            setWizard(false);
            await openDir(dir);
            if (properties) setPropertiesFor(dir);
          }}
          onClose={() => setWizard(false)}
          onImport={async (dir) => {
            if (!(await switchGuard())) return;
            setWizard(false);
            if (dir !== project) await openDir(dir);
            setImporting(dir);
          }}
        />
      )}
      {importing !== null && (
        <ImportView
          project={importing}
          onClose={() => setImporting(null)}
          onApplied={async (mapping) => {
            setImporting(null);
            await reloadFiles(mapping);
          }}
        />
      )}
      {tourRun && (
        <Tour
          tour={TOURS[tourRun.book]}
          index={tourRun.index}
          onIndex={(index) => setTourRun({ ...tourRun, index })}
          onClose={() => void endTour()}
          apply={(state) => applyTourRef.current(state)}
        />
      )}
      {guide !== null && <Guide
          start={guide}
          onClose={() => setGuide(null)}
          onExplorer={() => {
            setGuide(null);
            setExplorer(true);
          }}
          onTour={(book) => void startTour(book)}
        />}
      {conflict && (
        <SharedConflict
          file={conflict.file}
          other={conflict.other}
          kind={conflict.kind}
          items={conflict.items}
          onSettle={(choices) => {
            conflict.resolve({ choices });
            setConflict(null);
          }}
          onWhole={(keep) => {
            conflict.resolve({ whole: keep });
            setConflict(null);
          }}
          onCancel={() => {
            conflict.resolve(null);
            setConflict(null);
          }}
        />
      )}
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
      {importingGolden && current && (
        <GoldenImport
          mapping={mappingName(current)}
          taken={cases.map((c) => c.name)}
          onImport={importCase}
          onClose={() => setImportingGolden(false)}
        />
      )}
      {versionControl && project && (
        <VersionControl
          project={project}
          onClose={() => setVersionControl(false)}
          onChanged={() => void reloadFiles(current ? mappingName(current) : null)}
          ensureSaved={() => guardRef.current("Save before continuing?", "Continue without saving")}
        />
      )}
      {loopOptions !== null && tree && (() => {
        const rule = ruleAt(tree, loopOptions);
        if (!rule || rule.kind !== "loop") return null;
        const r = rule as unknown as Record<string, unknown>;
        return (
          <LoopOptions
            name={nameOf(rule)}
            values={{
              label: rule.label ?? null,
              order_by: (r.order_by as string | null) ?? null,
              index_start: Number(r.index_start ?? 0),
              when_empty: (r.when_empty as LoopOptionValues["when_empty"]) ?? null,
              parallel: (r.parallel as number | null) ?? null,
            }}
            onCancel={() => setLoopOptions(null)}
            onApply={(values) => {
              edit(loopOptions, (target) => {
                if (target.kind === "loop") Object.assign(target, values);
              });
              setLoopOptions(null);
            }}
          />
        );
      })()}
      {newRule && (
        <NewRuleDialog
          kind={newRule.kind}
          onSubmit={async (values) => {
            const error = await insertRule(newRule.kind, newRule.at, values);
            if (error === null) setNewRule(null);
            return error;
          }}
          onCancel={() => setNewRule(null)}
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
        {editing.length > 0 && (
          <div className="presence" title="Advisory: nothing is locked. Edits are merged when saved.">
            {editing.map((e) => (
              <span key={`${e.user}:${e.mapping}`} className={e.mapping === openMapping ? "same" : ""}>
                {e.user.replace(/@.*$/, "")} is editing {e.mapping}
                {e.mapping === openMapping ? " (this mapping)" : ""}
              </span>
            ))}
          </div>
        )}
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
