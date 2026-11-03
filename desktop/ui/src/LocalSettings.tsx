import type { ArtifactsState } from "./api";

export interface LocalState {
  /** The folder this user chose for Publish on this machine, or null (the project's setting). */
  publishDir: string | null;
  /** The folder this user builds in (a project in a synced folder), "-" = not a synced folder. */
  buildDir: string | null;
  artifacts: ArtifactsState | null;
}

interface Props {
  state: LocalState;
  /** The project is in a synced folder: it has a build folder of its own on each machine. */
  synced: boolean;
  onPublishDir: () => void;
  onBuildDir: () => void;
  onArtifacts: () => void;
}

function Row({ title, value, help, button, onClick }: { title: string; value: string; help: string; button: string; onClick: () => void }) {
  return (
    <div className="local-row">
      <div className="local-text">
        <strong>{title}</strong>
        <span className="local-value" title={value}>
          {value}
        </span>
        <small>{help}</small>
      </div>
      <button onClick={onClick}>{button}</button>
    </div>
  );
}

/** What belongs to this machine and repository rather than to `mapper.toml`: where Publish and the
 *  build write to, and whether the generated files are committed. Set once, so not in the toolbar. */
export function LocalSettings({ state, synced, onPublishDir, onBuildDir, onArtifacts }: Props) {
  const { artifacts } = state;
  return (
    <fieldset className="local-settings">
      <legend>This machine and repository</legend>
      <Row
        title="Publish folder"
        value={state.publishDir ?? "the project's setting (Publish › dir), else build/compiled"}
        help="Where Publish writes the files and manifest.json, on this machine. It beats the folder above."
        button="Change…"
        onClick={onPublishDir}
      />
      {synced && (
        <Row
          title="Build folder"
          value={state.buildDir && state.buildDir !== "-" ? state.buildDir : "not chosen"}
          help="The project is in a synced folder: nothing generated is written there, the build goes to a folder of this machine."
          button="Change…"
          onClick={onBuildDir}
        />
      )}
      <Row
        title="Generated files"
        value={
          artifacts === null || artifacts.mode === "unknown"
            ? "not in a git repository: nothing to commit or ignore"
            : artifacts.mode === "committed"
              ? `committed (${artifacts.tracked.length} in the repository)`
              : "not committed: git ignores them and CI builds them"
        }
        help="Whether build/compiled is committed with the sources, or left to CI (.gitignore)."
        button="Change…"
        onClick={onArtifacts}
      />
    </fieldset>
  );
}
