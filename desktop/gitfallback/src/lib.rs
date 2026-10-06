//! git operations for the desktop tool when the `git` binary is not installed, on gitoxide
//! (`gix` 0.88). Everything the Python side (`cli/gitops.py`) needs of git: state, staging,
//! commit, fetch + rebase, the conflicted index, abort, push, config. Results are JSON; paths are
//! relative to the project's folder (which may be a folder of a bigger repository).
//!
//! What gitoxide cannot do, found by trying it (docs/ARCHITECTURE.md, §Version control, §Without
//! git): no rebase, no stash and no push exist in `gix`: the rebase is a replay of the commits by
//! tree merges, the push is the send-pack protocol written on the transport (`push`); a commit
//! runs no hook; a repository on a local path needs `git upload-pack`, and a *named* credential
//! helper needs `git credential-<name>`.

use gix::bstr::{BStr, BString, ByteSlice};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

pub type R<T> = Result<T, String>;

fn s<E: std::fmt::Debug>(e: E) -> String {
    format!("{e:?}")
}

const STATE_FILE: &str = "j2jme-rebase.json";

pub struct Ctx {
    pub repo: gix::Repository,
    workdir: PathBuf,
    /// the project's folder from the repository's root, `""` or `"a/b/"`
    prefix: String,
}

impl Ctx {
    pub fn open(project: &Path) -> R<Ctx> {
        let repo = gix::discover(project).map_err(s)?;
        let workdir = repo
            .workdir()
            .ok_or("a bare repository has no project in it")?
            .to_path_buf();
        let proj = std::fs::canonicalize(project).map_err(s)?;
        let wd = std::fs::canonicalize(&workdir).map_err(s)?;
        let rel = proj.strip_prefix(&wd).map_err(s)?;
        let mut prefix = rel.to_string_lossy().replace('\\', "/");
        if !prefix.is_empty() {
            prefix.push('/');
        }
        Ok(Ctx {
            repo,
            workdir,
            prefix,
        })
    }

    fn full(&self, rel: &str) -> String {
        format!("{}{}", self.prefix, rel)
    }

    fn rel<'a>(&self, repo_rel: &'a str) -> Option<&'a str> {
        repo_rel.strip_prefix(self.prefix.as_str())
    }

    fn path_on_disk(&self, repo_rel: &str) -> PathBuf {
        self.workdir.join(repo_rel)
    }

    fn patterns(&self, specs: &[String]) -> Vec<BString> {
        if specs.is_empty() {
            return if self.prefix.is_empty() {
                vec![]
            } else {
                vec![BString::from(self.prefix.trim_end_matches('/'))]
            };
        }
        specs.iter().map(|p| BString::from(self.full(p))).collect()
    }

    fn git_dir(&self) -> &Path {
        self.repo.git_dir()
    }

    fn rebase_state_path(&self) -> PathBuf {
        self.git_dir().join(STATE_FILE)
    }

    fn rebasing(&self) -> bool {
        let g = self.git_dir();
        self.rebase_state_path().exists()
            || g.join("rebase-merge").is_dir()
            || g.join("rebase-apply").is_dir()
    }
}

// --- state ------------------------------------------------------------------------------------

/// A change under the given specs: `(repo-relative path, XY code as git's short format)`.
fn changes(ctx: &Ctx, specs: &[String]) -> R<Vec<(String, String)>> {
    use gix::status::index_worktree::iter::Summary;
    let iter = ctx
        .repo
        .status(gix::progress::Discard)
        .map_err(s)?
        .untracked_files(gix::status::UntrackedFiles::Files)
        .into_iter(ctx.patterns(specs))
        .map_err(s)?;
    let mut map: std::collections::BTreeMap<String, [char; 2]> = Default::default();
    for item in iter {
        match item.map_err(s)? {
            gix::status::Item::IndexWorktree(i) => {
                let Some(summary) = i.summary() else { continue };
                let y = match summary {
                    Summary::Added => '?',
                    Summary::Removed => 'D',
                    Summary::Modified => 'M',
                    Summary::TypeChange => 'T',
                    Summary::Conflict => 'U',
                    Summary::Renamed | Summary::Copied => 'M',
                    Summary::IntentToAdd => 'A',
                };
                let e = map.entry(i.rela_path().to_string()).or_insert([' ', ' ']);
                e[1] = y;
            }
            gix::status::Item::TreeIndex(c) => {
                let x = match &c {
                    gix::diff::index::Change::Addition { .. } => 'A',
                    gix::diff::index::Change::Deletion { .. } => 'D',
                    gix::diff::index::Change::Modification { .. } => 'M',
                    gix::diff::index::Change::Rewrite { .. } => 'R',
                };
                let e = map.entry(c.location().to_string()).or_insert([' ', ' ']);
                e[0] = x;
            }
        }
    }
    Ok(map
        .into_iter()
        .map(|(p, [x, y])| {
            let code = if y == '?' {
                "??".to_string()
            } else {
                format!("{x}{y}")
            };
            (p, code)
        })
        .collect())
}

/// The index file, or an empty one when there is none yet (a repository that was just created has
/// no index file until something is staged; gitoxide's `open_index` fails there, git does not).
fn load_index(repo: &gix::Repository) -> R<gix::index::File> {
    if !repo.index_path().exists() {
        return Ok(gix::index::File::from_state(
            gix::index::State::new(repo.object_hash()),
            repo.index_path(),
        ));
    }
    repo.open_index().map_err(s)
}

fn unmerged(ctx: &Ctx) -> R<Vec<String>> {
    let index = load_index(&ctx.repo)?;
    let mut paths = BTreeSet::new();
    for e in index.entries() {
        if e.stage() != gix::index::entry::Stage::Unconflicted {
            paths.insert(e.path(&index).to_string());
        }
    }
    Ok(paths
        .into_iter()
        .filter_map(|p| ctx.rel(&p).map(str::to_string))
        .collect())
}

pub fn state(project: &Path, specs: &[String]) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let repo = &ctx.repo;
    let head_name = repo.head_name().map_err(s)?;
    let branch = head_name.as_ref().map(|n| n.shorten().to_string());
    let mut upstream = Value::Null;
    let (mut ahead, mut behind) = (0usize, 0usize);
    if let (Some(name), Ok(head)) = (&head_name, repo.head_id()) {
        if let Some(tracking) =
            repo.branch_remote_tracking_ref_name(name.as_ref(), gix::remote::Direction::Fetch)
        {
            let tracking = tracking.map_err(s)?;
            if let Ok(mut r) = repo.find_reference(tracking.as_ref()) {
                let up = r.peel_to_id().map_err(s)?.detach();
                let head = head.detach();
                upstream = json!(tracking.shorten().to_string());
                ahead = repo
                    .rev_walk([head])
                    .with_hidden([up])
                    .all()
                    .map_err(s)?
                    .count();
                behind = repo
                    .rev_walk([up])
                    .with_hidden([head])
                    .all()
                    .map_err(s)?
                    .count();
            }
        }
    }
    let list: Vec<Value> = changes(&ctx, specs)?
        .into_iter()
        .filter_map(|(p, code)| ctx.rel(&p).map(|r| json!({"path": r, "code": code})))
        .collect();
    Ok(json!({
        "branch": branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "rebasing": ctx.rebasing(),
        "changes": list,
        "conflicts": unmerged(&ctx)?,
    }))
}

// --- the index and the work tree ---------------------------------------------------------------

fn kind_of(path: &Path) -> R<gix::object::tree::EntryKind> {
    use gix::object::tree::EntryKind;
    let meta = std::fs::symlink_metadata(path).map_err(s)?;
    if meta.file_type().is_symlink() {
        return Ok(EntryKind::Link);
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if meta.permissions().mode() & 0o111 != 0 {
            return Ok(EntryKind::BlobExecutable);
        }
    }
    Ok(EntryKind::Blob)
}

/// The bytes of a file as git stores them: the clone's filters applied (line ends with
/// `core.autocrlf` / `eol`, `ident`, a `filter` driver such as LFS), as `git add` does.
fn to_git(ctx: &Ctx, repo_rel: &str, full: &Path) -> R<Vec<u8>> {
    use std::io::Read;
    let (mut pipeline, index) = ctx.repo.filter_pipeline(None).map_err(s)?;
    let file = std::fs::File::open(full).map_err(s)?;
    let mut outcome = pipeline
        .convert_to_git(file, Path::new(repo_rel), &index)
        .map_err(s)?;
    let mut out = Vec::new();
    outcome.read_to_end(&mut out).map_err(s)?;
    Ok(out)
}

fn blob_of(ctx: &Ctx, path: &Path, kind: gix::object::tree::EntryKind) -> R<gix::ObjectId> {
    let bytes = if kind == gix::object::tree::EntryKind::Link {
        gix::path::into_bstr(std::fs::read_link(path).map_err(s)?)
            .into_owned()
            .into()
    } else {
        let rel = path
            .strip_prefix(&ctx.workdir)
            .map_err(s)?
            .to_string_lossy()
            .replace('\\', "/");
        to_git(ctx, &rel, path)?
    };
    Ok(ctx.repo.write_blob(bytes).map_err(s)?.detach())
}

fn mode_of(kind: gix::object::tree::EntryKind) -> gix::index::entry::Mode {
    use gix::index::entry::Mode;
    use gix::object::tree::EntryKind;
    match kind {
        EntryKind::BlobExecutable => Mode::FILE_EXECUTABLE,
        EntryKind::Link => Mode::SYMLINK,
        _ => Mode::FILE,
    }
}

/// Set the stage-0 entry of `repo_rel` to what is on disk (or remove it if the file is gone).
fn index_set_from_disk(ctx: &Ctx, index: &mut gix::index::File, repo_rel: &str) -> R<()> {
    index.remove_entries(|_, p, _| p == repo_rel.as_bytes().as_bstr());
    let full = ctx.path_on_disk(repo_rel);
    if std::fs::symlink_metadata(&full).is_ok() {
        let kind = kind_of(&full)?;
        let id = blob_of(ctx, &full, kind)?;
        let meta = gix::index::fs::Metadata::from_path_no_follow(&full).map_err(s)?;
        let stat = gix::index::entry::Stat::from_fs(&meta).map_err(s)?;
        index.dangerously_push_entry(
            stat,
            id,
            gix::index::entry::Flags::empty(),
            mode_of(kind),
            repo_rel.as_bytes().as_bstr(),
        );
    }
    index.sort_entries();
    Ok(())
}

fn write_index(index: &mut gix::index::File) -> R<()> {
    // the cached trees describe the entries as they were: git trusts them, so they must go
    // (found by `git diff --cached` calling a modified file "added")
    index.remove_tree();
    index.remove_resolve_undo();
    index.write(Default::default()).map_err(s)?;
    Ok(())
}

/// `git add -A -- specs`: what is on disk under `specs` becomes the stage-0 entries.
pub fn add(project: &Path, specs: &[String]) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let mut index = load_index(&ctx.repo)?;
    let list = changes(&ctx, specs)?;
    for (path, code) in &list {
        if code.as_bytes()[1] != b' ' || code == "??" {
            index_set_from_disk(&ctx, &mut index, path)?;
        }
    }
    write_index(&mut index)?;
    Ok(json!({"staged": list.len()}))
}

/// `git rm -r --cached -- spec`.
pub fn rm_cached(project: &Path, spec: &str) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let mut index = load_index(&ctx.repo)?;
    let dir = format!("{}/", ctx.full(spec).trim_end_matches('/'));
    let exact = ctx.full(spec);
    let mut removed = 0usize;
    index.remove_entries(|_, p, _| {
        let hit = p == exact.as_bytes().as_bstr() || p.starts_with(dir.as_bytes());
        if hit {
            removed += 1;
        }
        hit
    });
    write_index(&mut index)?;
    Ok(json!({"removed": removed}))
}

/// `git ls-files -- spec` (stage 0, from the project's folder).
pub fn ls_files(project: &Path, spec: &str) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let index = load_index(&ctx.repo)?;
    let dir = format!("{}/", ctx.full(spec).trim_end_matches('/'));
    let exact = ctx.full(spec);
    let mut out = vec![];
    for e in index.entries() {
        if e.stage() != gix::index::entry::Stage::Unconflicted {
            continue;
        }
        let p = e.path(&index).to_string();
        if p == exact || p.starts_with(&dir) {
            if let Some(r) = ctx.rel(&p) {
                out.push(r.to_string());
            }
        }
    }
    Ok(json!(out))
}

/// `git check-ignore --no-index -- path`: what the rules say, tracked or not.
pub fn check_ignore(project: &Path, path: &str) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let index = ctx.repo.index_or_empty().map_err(s)?;
    let mut stack = ctx
        .repo
        .excludes(
            &index,
            None,
            gix::worktree::stack::state::ignore::Source::WorktreeThenIdMappingIfNotSkipped,
        )
        .map_err(s)?;
    let full = ctx.full(path);
    let platform = stack
        .at_path(&full, Some(gix::index::entry::Mode::FILE))
        .map_err(s)?;
    Ok(json!(platform.is_excluded()))
}

// --- commit ------------------------------------------------------------------------------------

fn paths_to_commit(ctx: &Ctx, specs: &[String]) -> R<Vec<String>> {
    Ok(changes(ctx, specs)?
        .into_iter()
        .filter(|(_, code)| !code.contains('U'))
        .map(|(p, _)| p)
        .collect())
}

/// `git commit --only -- specs`: HEAD plus what is on disk under `specs`, nothing else; the index
/// moves for those paths only (whatever else is staged stays staged).
pub fn commit(project: &Path, message: &str, specs: &[String]) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let repo = &ctx.repo;
    let paths = paths_to_commit(&ctx, specs)?;
    // the first commit of a repository has no HEAD yet: it starts from the empty tree, with no parent
    let head = repo.head_commit().ok();
    let head_tree = match &head {
        Some(h) => h.tree_id().map_err(s)?.detach(),
        None => repo.empty_tree().id,
    };
    let mut editor = repo.edit_tree(head_tree).map_err(s)?;
    for path in &paths {
        let full = ctx.path_on_disk(path);
        if std::fs::symlink_metadata(&full).is_ok() {
            let kind = kind_of(&full)?;
            let id = blob_of(&ctx, &full, kind)?;
            editor.upsert(path.as_str(), kind, id).map_err(s)?;
        } else {
            editor.remove(path.as_str()).map_err(s)?;
        }
    }
    let tree_id = editor.write().map_err(s)?.detach();
    if tree_id == head_tree && head.is_some() {
        return Ok(json!({"committed": false}));
    }
    let parents: Vec<gix::ObjectId> = head.iter().map(|h| h.id).collect();
    let id = repo.commit("HEAD", message, tree_id, parents).map_err(s)?;
    let mut index = load_index(repo)?;
    for path in &paths {
        index_set_from_disk(&ctx, &mut index, path)?;
    }
    write_index(&mut index)?;
    Ok(json!({"committed": true, "commit": id.to_hex_with_len(7).to_string()}))
}

/// The text of `rev:path` (`HEAD`), or None.
pub fn show_head(project: &Path, path: &str) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let Ok(head) = ctx.repo.head_commit() else {
        return Ok(Value::Null); // nothing is committed yet
    };
    let tree = head.tree().map_err(s)?;
    let Some(entry) = tree.lookup_entry_by_path(ctx.full(path)).map_err(s)? else {
        return Ok(Value::Null);
    };
    let blob = ctx.repo.find_blob(entry.object_id()).map_err(s)?;
    Ok(json!(blob.data.to_str_lossy()))
}

// --- fetch, rebase -----------------------------------------------------------------------------
//
// gitoxide has no rebase and no stash. A rebase here is a replay of our commits, one by one, by
// merging trees (`merge_trees`, which honours the clone's merge drivers); it stops when a merge
// leaves a conflict, with the work tree and the index as git leaves them (stages 1-3, markers),
// and goes on when the conflicted files are resolved. The state of a stopped rebase is the
// tool's own (`.git/j2jme-rebase.json`), not git's: `git rebase --continue` does not know it.

#[derive(Serialize, Deserialize, Clone)]
struct Rebase {
    head_ref: String,
    orig_head: String,
    onto: String,
    /// the new head so far
    cur: String,
    /// the commit being replayed, when stopped on conflicts
    current: Option<String>,
    /// the commits still to replay, oldest first
    todo: Vec<String>,
    /// the tree of the stop (conflict markers in the files that conflict)
    stop_tree: Option<String>,
    stop_conflicts: Vec<String>,
    /// every path the rebase has written to the work tree: what an abort puts back
    touched: Vec<String>,
}

fn load_state(ctx: &Ctx) -> R<Rebase> {
    let text = std::fs::read_to_string(ctx.rebase_state_path())
        .map_err(|_| "no rebase in progress".to_string())?;
    serde_json::from_str(&text).map_err(s)
}

fn save_state(ctx: &Ctx, st: &Rebase) -> R<()> {
    std::fs::write(
        ctx.rebase_state_path(),
        serde_json::to_string_pretty(st).map_err(s)?,
    )
    .map_err(s)
}

fn oid(text: &str) -> R<gix::ObjectId> {
    gix::ObjectId::from_hex(text.as_bytes()).map_err(s)
}

type Credentials = Option<(String, String)>;

/// The authentication of a connection: the user's `credentials` when the tool has asked for them,
/// else the clone's configuration (askpass, a helper given by path, credentials in the URL). A
/// *named* helper (`store`, `manager`...) runs as `git credential-<name>`, so it needs git.
fn authenticator(
    repo: &gix::Repository,
    url: gix::url::Url,
    credentials: Credentials,
) -> R<impl FnMut(gix::credentials::helper::Action) -> gix::credentials::protocol::Result> {
    let (mut cascade, _action, prompt) =
        repo.config_snapshot().credential_helpers(url).map_err(s)?;
    Ok(
        move |action: gix::credentials::helper::Action| match (&credentials, &action) {
            (Some((user, pass)), gix::credentials::helper::Action::Get(ctx)) => {
                Ok(Some(gix::credentials::protocol::Outcome {
                    identity: gix::sec::identity::Account {
                        username: user.clone(),
                        password: pass.clone(),
                        oauth_refresh_token: None,
                    },
                    next: gix::credentials::helper::NextAction::from(ctx.clone()),
                }))
            }
            (Some(_), _) => Ok(None),
            _ => cascade.invoke(action, prompt.clone()),
        },
    )
}

fn fetch(ctx: &Ctx, remote_name: &BStr, credentials: Credentials) -> R<()> {
    let remote = ctx.repo.find_remote(remote_name).map_err(s)?;
    let url = remote
        .url(gix::remote::Direction::Fetch)
        .ok_or("the remote has no URL")?
        .clone();
    let authenticate = authenticator(&ctx.repo, url, credentials)?;
    let connection = remote
        .connect(gix::remote::Direction::Fetch)
        .map_err(|e| format!("connect: {e:?}"))?
        .with_credentials(authenticate);
    let prepared = connection
        .prepare_fetch(gix::progress::Discard, Default::default())
        .map_err(|e| format!("prepare: {e:?}"))?;
    prepared
        .receive(gix::progress::Discard, &gix::interrupt::IS_INTERRUPTED)
        .map_err(|e| format!("receive: {e:?}"))?;
    Ok(())
}

fn tree_of(ctx: &Ctx, commit: gix::ObjectId) -> R<gix::ObjectId> {
    Ok(ctx
        .repo
        .find_commit(commit)
        .map_err(s)?
        .tree_id()
        .map_err(s)?
        .detach())
}

/// Paths that differ between two trees.
fn diff_paths(ctx: &Ctx, a: gix::ObjectId, b: gix::ObjectId) -> R<BTreeSet<String>> {
    let (ta, tb) = (
        ctx.repo.find_tree(a).map_err(s)?,
        ctx.repo.find_tree(b).map_err(s)?,
    );
    let list = ctx
        .repo
        .diff_tree_to_tree(Some(&ta), Some(&tb), None)
        .map_err(s)?;
    let mut out = BTreeSet::new();
    for c in &list {
        if c.entry_mode().is_tree() {
            continue; // a directory that changed: its files are listed on their own
        }
        out.insert(c.location().to_string());
        if let gix::object::tree::diff::ChangeDetached::Rewrite {
            source_location, ..
        } = c
        {
            out.insert(source_location.to_string()); // a rename touches both paths
        }
    }
    Ok(out)
}

fn whole_repo_changes(ctx: &Ctx) -> R<Vec<(String, String)>> {
    let all = Ctx {
        repo: ctx.repo.clone(),
        workdir: ctx.workdir.clone(),
        prefix: String::new(),
    };
    changes(&all, &[])
}

fn entry_kind(mode: gix::index::entry::Mode) -> gix::object::tree::EntryKind {
    use gix::index::entry::Mode;
    use gix::object::tree::EntryKind;
    if mode == Mode::FILE_EXECUTABLE {
        EntryKind::BlobExecutable
    } else if mode == Mode::SYMLINK {
        EntryKind::Link
    } else if mode == Mode::COMMIT {
        EntryKind::Commit
    } else {
        EntryKind::Blob
    }
}

fn write_blob_to_disk(
    ctx: &Ctx,
    repo_rel: &str,
    id: gix::ObjectId,
    mode: gix::index::entry::Mode,
) -> R<()> {
    let full = ctx.path_on_disk(repo_rel);
    if let Some(parent) = full.parent() {
        std::fs::create_dir_all(parent).map_err(s)?;
    }
    if std::fs::symlink_metadata(&full).is_ok() {
        std::fs::remove_file(&full).map_err(s)?;
    }
    let blob = ctx.repo.find_blob(id).map_err(s)?;
    if mode == gix::index::entry::Mode::SYMLINK {
        #[cfg(unix)]
        std::os::unix::fs::symlink(gix::path::from_bstr(blob.data.as_bstr()), &full).map_err(s)?;
        #[cfg(not(unix))]
        return Err(format!(
            "{repo_rel}: a symbolic link cannot be written here"
        ));
    } else if mode == gix::index::entry::Mode::COMMIT {
        std::fs::create_dir_all(&full).map_err(s)?; // a submodule: only its place
    } else {
        std::fs::write(&full, to_worktree(ctx, repo_rel, &blob.data)?).map_err(s)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let bits = if mode == gix::index::entry::Mode::FILE_EXECUTABLE {
                0o755
            } else {
                0o644
            };
            std::fs::set_permissions(&full, std::fs::Permissions::from_mode(bits)).map_err(s)?;
        }
    }
    Ok(())
}

/// The bytes of a blob as they are in the work tree (`core.autocrlf`, `eol`, `ident`, `filter`).
fn to_worktree(ctx: &Ctx, repo_rel: &str, data: &[u8]) -> R<Vec<u8>> {
    use gix::filter::plumbing::pipeline::convert::ToWorktreeOutcome;
    use std::io::Read;
    let (mut pipeline, _index) = ctx.repo.filter_pipeline(None).map_err(s)?;
    let outcome = pipeline
        .convert_to_worktree(data, repo_rel.as_bytes().as_bstr(), Default::default())
        .map_err(s)?;
    Ok(match outcome {
        ToWorktreeOutcome::Unchanged(bytes) => bytes.to_vec(),
        ToWorktreeOutcome::Buffer(bytes) => bytes.to_vec(),
        ToWorktreeOutcome::Process(
            gix::filter::plumbing::driver::apply::MaybeDelayed::Immediate(mut read),
        ) => {
            let mut out = Vec::new();
            read.read_to_end(&mut out).map_err(s)?;
            out
        }
        ToWorktreeOutcome::Process(_) => {
            return Err(format!("{repo_rel}: a delayed filter result"))
        }
    })
}

fn prune_empty_dirs(ctx: &Ctx, repo_rel: &str) {
    let mut dir = ctx.path_on_disk(repo_rel);
    while dir.pop() && dir != ctx.workdir {
        if std::fs::remove_dir(&dir).is_err() {
            break;
        }
    }
}

fn stage_of(i: usize) -> gix::index::entry::Stage {
    use gix::index::entry::Stage;
    [Stage::Base, Stage::Ours, Stage::Theirs][i]
}

/// Make `paths` in the work tree and the index what `tree` says. Only these paths are touched, so
/// whatever else is staged or modified stays as it is. The conflicts that are left (`unresolved`)
/// become stages 1-3, and their file holds what the merge wrote into `tree` (the markers).
fn apply_paths(
    ctx: &Ctx,
    paths: &BTreeSet<String>,
    tree: gix::ObjectId,
    unresolved: &[&gix::merge::tree::Conflict],
) -> R<()> {
    let repo = &ctx.repo;
    let mut index = load_index(repo)?;
    let target = repo.find_tree(tree).map_err(s)?;
    let mut conflicted: std::collections::BTreeMap<
        String,
        [Option<(gix::ObjectId, gix::index::entry::Mode)>; 3],
    > = Default::default();
    for c in unresolved {
        let path = c.ours.location().to_string();
        let mut sides = [None, None, None];
        for (i, e) in c.entries().iter().enumerate() {
            if let Some(e) = e {
                sides[i] = Some((e.id, gix::index::entry::Mode::from(e.mode)));
            }
        }
        conflicted.insert(path, sides);
    }
    let mut all: BTreeSet<String> = paths.clone();
    all.extend(conflicted.keys().cloned());
    for path in &all {
        index.remove_entries(|_, p, _| p == path.as_bytes().as_bstr());
        let in_tree = target.lookup_entry_by_path(path).map_err(s)?;
        if let Some(sides) = conflicted.get(path) {
            // the file as the merge left it, else a side that exists
            if let Some(entry) = &in_tree {
                write_blob_to_disk(ctx, path, entry.object_id(), entry.mode().into())?;
            } else if let Some((id, mode)) = sides[2].or(sides[1]) {
                write_blob_to_disk(ctx, path, id, mode)?;
            }
            for (i, side) in sides.iter().enumerate() {
                if let Some((id, mode)) = side {
                    index.dangerously_push_entry(
                        Default::default(),
                        *id,
                        gix::index::entry::Flags::from_stage(stage_of(i)),
                        *mode,
                        path.as_bytes().as_bstr(),
                    );
                }
            }
            continue;
        }
        match in_tree {
            Some(entry) => {
                let mode: gix::index::entry::Mode = entry.mode().into();
                write_blob_to_disk(ctx, path, entry.object_id(), mode)?;
                let meta = gix::index::fs::Metadata::from_path_no_follow(&ctx.path_on_disk(path))
                    .map_err(s)?;
                let stat = gix::index::entry::Stat::from_fs(&meta).map_err(s)?;
                index.dangerously_push_entry(
                    stat,
                    entry.object_id(),
                    gix::index::entry::Flags::empty(),
                    mode,
                    path.as_bytes().as_bstr(),
                );
            }
            None => {
                let full = ctx.path_on_disk(path);
                if std::fs::symlink_metadata(&full).is_ok() {
                    std::fs::remove_file(&full).map_err(s)?;
                    prune_empty_dirs(ctx, path);
                }
            }
        }
    }
    index.sort_entries();
    write_index(&mut index)
}

fn replay(ctx: &Ctx, mut st: Rebase) -> R<Value> {
    let repo = &ctx.repo;
    let how = gix::merge::tree::TreatAsUnresolved::default();
    while let Some(next) = st.todo.first().cloned() {
        let c_id = oid(&next)?;
        let commit = repo.find_commit(c_id).map_err(s)?;
        let parent = commit
            .parent_ids()
            .next()
            .ok_or("a root commit cannot be replayed")?
            .detach();
        let (parent_tree, cur_tree, c_tree) = (
            tree_of(ctx, parent)?,
            tree_of(ctx, oid(&st.cur)?)?,
            tree_of(ctx, c_id)?,
        );
        let labels = gix::merge::blob::builtin_driver::text::Labels {
            ancestor: Some("base".into()),
            current: Some("remote".into()),
            other: Some("mine".into()),
        };
        let options = repo.tree_merge_options().map_err(s)?;
        let mut outcome = repo
            .merge_trees(parent_tree, cur_tree, c_tree, labels, options)
            .map_err(s)?;
        let unresolved = outcome.has_unresolved_conflicts(how);
        let merged = outcome.tree.write().map_err(s)?.detach();
        st.todo.remove(0);
        if unresolved {
            let list: Vec<&gix::merge::tree::Conflict> = outcome
                .conflicts
                .iter()
                .filter(|c| c.is_unresolved(how))
                .collect();
            let orig_tree = tree_of(ctx, oid(&st.orig_head)?)?;
            let mut paths = diff_paths(ctx, orig_tree, merged)?;
            paths.extend(st.touched.iter().cloned());
            apply_paths(ctx, &paths, merged, &list)?;
            st.touched = paths.into_iter().collect();
            st.stop_conflicts = list.iter().map(|c| c.ours.location().to_string()).collect();
            st.stop_tree = Some(merged.to_string());
            st.current = Some(next);
            save_state(ctx, &st)?;
            let shown: Vec<String> = st
                .stop_conflicts
                .iter()
                .filter_map(|p| ctx.rel(p).map(str::to_string))
                .collect();
            return Ok(json!({"finished": false, "conflicts": shown}));
        }
        // a commit whose changes are all in already is dropped, as `git rebase` does
        if merged != cur_tree {
            st.cur = new_commit(ctx, &commit, merged, oid(&st.cur)?)?.to_string();
        }
    }
    finish(ctx, st)
}

fn new_commit(
    ctx: &Ctx,
    like: &gix::Commit<'_>,
    tree: gix::ObjectId,
    parent: gix::ObjectId,
) -> R<gix::ObjectId> {
    let repo = &ctx.repo;
    let committer = repo
        .committer()
        .ok_or("no committer identity is configured")?
        .map_err(s)?
        .to_owned()
        .map_err(s)?;
    let decoded = like.decode().map_err(s)?;
    let commit = gix::objs::Commit {
        tree,
        parents: [parent].into(),
        author: decoded.author().map_err(s)?.to_owned().map_err(s)?,
        committer,
        encoding: None,
        message: decoded.message.to_owned(),
        extra_headers: vec![],
    };
    Ok(repo.write_object(&commit).map_err(s)?.detach())
}

fn finish(ctx: &Ctx, st: Rebase) -> R<Value> {
    use gix::refs::transaction::PreviousValue;
    let cur = oid(&st.cur)?;
    let target = tree_of(ctx, cur)?;
    let orig_tree = tree_of(ctx, oid(&st.orig_head)?)?;
    let mut paths = diff_paths(ctx, orig_tree, target)?;
    paths.extend(st.touched.iter().cloned());
    apply_paths(ctx, &paths, target, &[])?;
    ctx.repo
        .reference(
            st.head_ref.as_str(),
            cur,
            PreviousValue::MustExistAndMatch(gix::refs::Target::Object(oid(&st.orig_head)?)),
            "pull --rebase: finished",
        )
        .map_err(s)?;
    let _ = std::fs::remove_file(ctx.rebase_state_path());
    Ok(json!({"finished": true, "conflicts": []}))
}

pub fn pull(project: &Path, credentials: Credentials) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let repo = &ctx.repo;
    if ctx.rebasing() {
        return Err("a rebase is in progress: finish or abort it first".into());
    }
    let head_ref = repo
        .head_name()
        .map_err(s)?
        .ok_or("HEAD is not on a branch")?;
    let tracking = repo
        .branch_remote_tracking_ref_name(head_ref.as_ref(), gix::remote::Direction::Fetch)
        .ok_or("this branch has no upstream to pull from")?
        .map_err(s)?;
    let remote = repo
        .branch_remote_name(head_ref.shorten(), gix::remote::Direction::Fetch)
        .ok_or("this branch has no remote")?;
    fetch(&ctx, remote.as_bstr(), credentials)?;
    let head = repo.head_id().map_err(s)?.detach();
    let upstream = repo
        .find_reference(tracking.as_ref())
        .map_err(s)?
        .peel_to_id()
        .map_err(s)?
        .detach();
    if head == upstream {
        return Ok(json!({"finished": true, "conflicts": []}));
    }
    let base = repo.merge_base(head, upstream).ok().map(|b| b.detach());
    if base == Some(upstream) {
        return Ok(json!({"finished": true, "conflicts": []})); // only ahead
    }
    // the work tree must not hold anything the pull is going to change
    let touched = diff_paths(&ctx, tree_of(&ctx, head)?, tree_of(&ctx, upstream)?)?;
    let dirty: Vec<String> = whole_repo_changes(&ctx)?
        .into_iter()
        .filter(|(p, c)| touched.contains(p) && c != "??")
        .map(|(p, _)| p)
        .collect();
    if !dirty.is_empty() {
        return Err(format!(
            "commit or discard your changes first: the pull changes these files too, and without git there is no stash: {}",
            dirty.join(", ")
        ));
    }
    let mut todo: Vec<String> = vec![];
    if base != Some(head) {
        let walk = repo
            .rev_walk([head])
            .with_hidden([upstream])
            .all()
            .map_err(s)?;
        let mut chain = vec![];
        for info in walk {
            let info = info.map_err(s)?;
            if repo.find_commit(info.id).map_err(s)?.parent_ids().count() > 1 {
                return Err(
                    "a merge commit among the commits to replay: it cannot be rebased here".into(),
                );
            }
            chain.push(info.id);
        }
        chain.reverse();
        todo = chain.iter().map(|c| c.to_string()).collect();
    }
    let st = Rebase {
        head_ref: head_ref.as_bstr().to_string(),
        orig_head: head.to_string(),
        onto: upstream.to_string(),
        cur: upstream.to_string(),
        current: None,
        todo,
        stop_tree: None,
        stop_conflicts: vec![],
        touched: vec![],
    };
    save_state(&ctx, &st)?;
    replay(&ctx, st)
}

pub fn rebase_continue(project: &Path) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let mut st = load_state(&ctx)?;
    let left = unmerged(&ctx)?;
    if !left.is_empty() {
        return Ok(json!({"finished": false, "conflicts": left}));
    }
    if let Some(current) = st.current.take() {
        // the tree of the stop, with what was done to the files that conflicted
        let stop = oid(st.stop_tree.as_deref().ok_or("the stop has no tree")?)?;
        let index = load_index(&ctx.repo)?;
        let mut editor = ctx.repo.edit_tree(stop).map_err(s)?;
        for path in &st.stop_conflicts {
            match index.entry_by_path_and_stage(
                path.as_bytes().as_bstr(),
                gix::index::entry::Stage::Unconflicted,
            ) {
                Some(e) => {
                    editor
                        .upsert(path.as_str(), entry_kind(e.mode), e.id)
                        .map_err(s)?;
                }
                None => {
                    editor.remove(path.as_str()).map_err(s)?;
                }
            }
        }
        let tree = editor.write().map_err(s)?.detach();
        let commit = ctx.repo.find_commit(oid(&current)?).map_err(s)?;
        // resolved to what is there already (the other side chosen): the commit is dropped
        if tree != tree_of(&ctx, oid(&st.cur)?)? {
            st.cur = new_commit(&ctx, &commit, tree, oid(&st.cur)?)?.to_string();
        }
        st.stop_tree = None;
        st.stop_conflicts = vec![];
        save_state(&ctx, &st)?;
    }
    replay(&ctx, st)
}

pub fn rebase_abort(project: &Path) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let st = load_state(&ctx)?;
    let orig = tree_of(&ctx, oid(&st.orig_head)?)?;
    let paths: BTreeSet<String> = st.touched.iter().cloned().collect();
    apply_paths(&ctx, &paths, orig, &[])?;
    let _ = std::fs::remove_file(ctx.rebase_state_path());
    Ok(json!({"ok": true}))
}

/// The text of the file at index stage `n` (1 base, 2 what we rebase onto, 3 ours being replayed),
/// or null.
pub fn stage_text(project: &Path, n: u8, path: &str) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let index = load_index(&ctx.repo)?;
    let want = match n {
        1 => gix::index::entry::Stage::Base,
        2 => gix::index::entry::Stage::Ours,
        3 => gix::index::entry::Stage::Theirs,
        _ => return Err("stage is 1, 2 or 3".into()),
    };
    let full = ctx.full(path);
    match index.entry_by_path_and_stage(full.as_bytes().as_bstr(), want) {
        Some(e) => {
            let blob = ctx.repo.find_blob(e.id).map_err(s)?;
            Ok(json!(blob.data.to_str_lossy()))
        }
        None => Ok(Value::Null),
    }
}

/// `git add -- path` for a file that was in conflict: what is on disk is stage 0.
pub fn mark_resolved(project: &Path, path: &str) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let mut index = load_index(&ctx.repo)?;
    index_set_from_disk(&ctx, &mut index, &ctx.full(path))?;
    write_index(&mut index)?;
    Ok(json!({"ok": true}))
}

pub fn config_set(project: &Path, key: &str, value: &str) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let path = ctx.git_dir().join("config");
    let mut file =
        gix::config::File::from_path_no_includes(path.clone(), gix::config::Source::Local)
            .map_err(s)?;
    let (section, sub, name) = split_key(key)?;
    file.set_raw_value_by(section, sub, name, value.as_bytes().as_bstr())
        .map_err(s)?;
    let mut out = std::fs::File::create(&path).map_err(s)?;
    file.write_to(&mut out).map_err(s)?;
    Ok(json!({"ok": true}))
}

/// Remove the whole section `name` / `subsection` (`merge.j2jme` is section `merge`, subsection `j2jme`).
pub fn config_remove_section(project: &Path, name: &str, subsection: Option<&str>) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let path = ctx.git_dir().join("config");
    let mut file =
        gix::config::File::from_path_no_includes(path.clone(), gix::config::Source::Local)
            .map_err(s)?;
    let removed = file
        .remove_section(name, subsection.map(|s| s.as_bytes().as_bstr()))
        .is_some();
    if removed {
        let mut out = std::fs::File::create(&path).map_err(s)?;
        file.write_to(&mut out).map_err(s)?;
    }
    Ok(json!({"removed": removed}))
}

pub fn config_get(project: &Path, key: &str) -> R<Value> {
    let ctx = Ctx::open(project)?;
    let path = ctx.git_dir().join("config");
    let file =
        gix::config::File::from_path_no_includes(path, gix::config::Source::Local).map_err(s)?;
    let (section, sub, name) = split_key(key)?;
    Ok(file
        .raw_value_by(section, sub, name)
        .map(|v| json!(v.to_str_lossy()))
        .unwrap_or(Value::Null))
}

/// `a.b.c` is section `a`, subsection `b`, key `c`; `a.c` has no subsection. A subsection may hold dots.
fn split_key(key: &str) -> R<(&str, Option<&BStr>, &str)> {
    let (head, name) = key
        .rsplit_once('.')
        .ok_or_else(|| format!("not a config key: {key}"))?;
    match head.split_once('.') {
        None => Ok((head, None, name)),
        Some((section, sub)) => Ok((section, Some(sub.as_bytes().as_bstr()), name)),
    }
}

// --- push --------------------------------------------------------------------------------------
//
// gitoxide cannot push (no send-pack in `gix`, `gix-protocol` or `gix-transport`: only the service
// name `git-receive-pack` and the handshake exist). Here it is written from the protocol (v0/v1
// send-pack, `report-status`) on the pieces that are there: the transport, the handshake with
// authentication, the object database; the pack is written by hand, one undeltified entry per object.

fn pack_entry(out: &mut Vec<u8>, kind: gix::object::Kind, data: &[u8]) -> R<()> {
    use std::io::Write;
    let type_bits: u8 = match kind {
        gix::object::Kind::Commit => 1,
        gix::object::Kind::Tree => 2,
        gix::object::Kind::Blob => 3,
        gix::object::Kind::Tag => 4,
    };
    let mut size = data.len();
    let mut byte = (type_bits << 4) | (size & 0x0f) as u8;
    size >>= 4;
    while size > 0 {
        out.push(byte | 0x80);
        byte = (size & 0x7f) as u8;
        size >>= 7;
    }
    out.push(byte);
    let mut z = flate2::write::ZlibEncoder::new(Vec::new(), flate2::Compression::default());
    z.write_all(data).map_err(s)?;
    out.extend(z.finish().map_err(s)?);
    Ok(())
}

/// The objects the remote lacks for `new`: its new commits and, for each, what changed in its tree
/// against its first parent (every entry of the tree for a root commit).
fn objects_to_send(
    ctx: &Ctx,
    new: gix::ObjectId,
    known: &[gix::ObjectId],
) -> R<Vec<gix::ObjectId>> {
    let repo = &ctx.repo;
    let hidden: Vec<gix::ObjectId> = known
        .iter()
        .copied()
        .filter(|id| repo.has_object(*id))
        .collect();
    let walk = repo.rev_walk([new]).with_hidden(hidden).all().map_err(s)?;
    let mut seen: BTreeSet<gix::ObjectId> = BTreeSet::new();
    let mut order: Vec<gix::ObjectId> = vec![];
    let mut push = |id: gix::ObjectId, order: &mut Vec<gix::ObjectId>| {
        if seen.insert(id) {
            order.push(id);
        }
    };
    for info in walk {
        let info = info.map_err(s)?;
        let commit = repo.find_commit(info.id).map_err(s)?;
        push(info.id, &mut order);
        let tree = commit.tree().map_err(s)?;
        let parent_tree = match commit.parent_ids().next() {
            Some(p) => Some(repo.find_commit(p).map_err(s)?.tree().map_err(s)?),
            None => None,
        };
        let changes = repo
            .diff_tree_to_tree(parent_tree.as_ref(), Some(&tree), None)
            .map_err(s)?;
        push(tree.id, &mut order);
        for c in &changes {
            let (mode, id) = c.entry_mode_and_id();
            if mode.is_commit() {
                continue; // a submodule's commit lives in another repository
            }
            push(id.to_owned(), &mut order);
        }
    }
    Ok(order)
}

fn build_pack(ctx: &Ctx, ids: &[gix::ObjectId]) -> R<Vec<u8>> {
    let mut pack = Vec::new();
    pack.extend_from_slice(b"PACK");
    pack.extend_from_slice(&2u32.to_be_bytes());
    pack.extend_from_slice(&(ids.len() as u32).to_be_bytes());
    for id in ids {
        let obj = ctx.repo.find_object(*id).map_err(s)?;
        pack_entry(&mut pack, obj.kind, &obj.data)?;
    }
    let mut hasher = gix::hash::hasher(gix::hash::Kind::Sha1);
    hasher.update(&pack);
    let digest = hasher.try_finalize().map_err(s)?;
    pack.extend_from_slice(digest.as_slice());
    Ok(pack)
}

/// What the remote answered to a push, as `(unpack status, [(ref, ok?, reason)])`. The reader has
/// already taken the packet lines apart: what is left is their text, one line each.
fn read_report(raw: &[u8]) -> (String, Vec<(String, bool, String)>) {
    let mut unpack = String::new();
    let mut refs = vec![];
    for line in String::from_utf8_lossy(raw).lines() {
        if let Some(rest) = line.strip_prefix("unpack ") {
            unpack = rest.to_string();
        } else if let Some(name) = line.strip_prefix("ok ") {
            refs.push((name.to_string(), true, String::new()));
        } else if let Some(rest) = line.strip_prefix("ng ") {
            let (name, why) = rest.split_once(' ').unwrap_or((rest, ""));
            refs.push((name.to_string(), false, why.to_string()));
        }
    }
    (unpack, refs)
}

pub fn push(project: &Path, credentials: Credentials) -> R<Value> {
    use gix::protocol::transport::client::blocking_io::Transport as _;
    use gix::protocol::transport::client::{MessageKind, WriteMode};
    use gix::protocol::transport::Service;
    use std::io::Write;
    let ctx = Ctx::open(project)?;
    let repo = &ctx.repo;
    let head_ref = repo
        .head_name()
        .map_err(s)?
        .ok_or("HEAD is not on a branch")?;
    let short = head_ref.shorten().to_string();
    let remote_name = repo
        .branch_remote_name(head_ref.shorten(), gix::remote::Direction::Push)
        .map(|n| n.as_bstr().to_string())
        .unwrap_or_else(|| "origin".into());
    let remote = repo.find_remote(remote_name.as_str()).map_err(s)?;
    let url = remote
        .url(gix::remote::Direction::Push)
        .or_else(|| remote.url(gix::remote::Direction::Fetch))
        .ok_or("the remote has no URL")?
        .clone();
    let target = repo
        .branch_remote_ref_name(head_ref.as_ref(), gix::remote::Direction::Push)
        .and_then(|r| r.ok())
        .map(|r| r.as_bstr().to_string())
        .unwrap_or_else(|| format!("refs/heads/{short}"));
    let new = repo.head_id().map_err(s)?.detach();

    let mut transport = gix::protocol::transport::client::blocking_io::connect::connect(
        url.clone(),
        gix::protocol::transport::client::blocking_io::connect::Options {
            version: gix::protocol::transport::Protocol::V1,
            ..Default::default()
        },
    )
    .map_err(|e| format!("connect: {e:?}"))?;
    let authenticate = authenticator(repo, url.clone(), credentials)?;
    let handshake = gix::protocol::handshake(
        &mut transport,
        Service::ReceivePack,
        authenticate,
        vec![],
        &mut gix::progress::Discard,
    )
    .map_err(|e| format!("handshake: {e:?}"))?;
    let advertised = handshake.refs.unwrap_or_default();
    let mut old = gix::ObjectId::null(gix::hash::Kind::Sha1);
    let mut known: Vec<gix::ObjectId> = vec![];
    for r in &advertised {
        let (name, id) = match r {
            gix::protocol::handshake::Ref::Direct {
                full_ref_name,
                object,
            } => (full_ref_name, *object),
            gix::protocol::handshake::Ref::Peeled {
                full_ref_name,
                object,
                ..
            } => (full_ref_name, *object),
            gix::protocol::handshake::Ref::Symbolic {
                full_ref_name,
                object,
                ..
            } => (full_ref_name, *object),
            gix::protocol::handshake::Ref::Unborn { .. } => continue,
        };
        known.push(id);
        if name.as_slice() == target.as_bytes() {
            old = id;
        }
    }
    if old == new {
        return Ok(json!({"ok": true, "pushed": false}));
    }
    if !old.is_null() {
        let reachable = repo.has_object(old)
            && repo
                .merge_base(new, old)
                .map(|b| b.detach() == old)
                .unwrap_or(false);
        if !reachable {
            return Err("the remote has commits you do not have: pull first".into());
        }
    }
    let ids = objects_to_send(&ctx, new, &known)?;
    let pack = build_pack(&ctx, &ids)?;

    let mut request = transport
        .request(WriteMode::Binary, MessageKind::Flush, false)
        .map_err(|e| format!("request: {e:?}"))?;
    let mut command = format!("{old} {new} {target}").into_bytes();
    command.push(0);
    command.extend_from_slice(b"report-status agent=j2jme");
    request.write_all(&command).map_err(s)?; // Binary mode: one packet line per write
    request.write_message(MessageKind::Flush).map_err(s)?;
    let (mut writer, reader) = request.into_parts();
    writer.write_all(&pack).map_err(s)?;
    writer.flush().map_err(s)?;
    drop(writer);
    let mut raw = Vec::new();
    {
        use std::io::Read;
        let mut reader = reader;
        reader.read_to_end(&mut raw).map_err(s)?;
    }
    let (unpack, refs) = read_report(&raw);
    if unpack != "ok" {
        return Err(format!("the remote could not unpack: {unpack}"));
    }
    for (name, ok, why) in &refs {
        if !ok {
            return Err(format!("the remote refused {name}: {why}"));
        }
    }
    Ok(json!({"ok": true, "pushed": true, "objects": ids.len()}))
}

// --- the entry point of `j2jme-desktop --git-helper` ---------------------------------------------

fn strings(v: &Value, key: &str) -> Vec<String> {
    v.get(key)
        .and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

fn text<'a>(v: &'a Value, key: &str) -> R<&'a str> {
    v.get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("the request has no `{key}`"))
}

fn credentials_of(v: &Value) -> Credentials {
    let c = v.get("credentials")?;
    Some((
        c.get("username")?.as_str()?.to_string(),
        c.get("password")?.as_str()?.to_string(),
    ))
}

/// True for a failure that more credentials could cure (the tool then asks the user for them).
fn needs_credentials(message: &str) -> bool {
    let m = message.to_lowercase();
    [
        "authentication",
        "credentials",
        "authenticat",
        "401",
        "403",
        "terminal prompts disabled",
    ]
    .iter()
    .any(|k| m.contains(k))
}

/// `git init -b main`: a new repository in `project`, on a branch called `main` (what the tool's
/// own projects and the remotes it meets use), with no commit yet.
fn init(project: &Path) -> R<Value> {
    gix::init(project).map_err(|e| e.to_string())?;
    std::fs::write(project.join(".git").join("HEAD"), "ref: refs/heads/main\n")
        .map_err(|e| e.to_string())?;
    Ok(json!({}))
}

/// One request `{op, project, ...}` -> `{ok, ...}` or `{ok: false, error, auth?}`.
pub fn run(request: &Value) -> Value {
    let result = (|| -> R<Value> {
        let project = PathBuf::from(text(request, "project")?);
        let project = project.as_path();
        match text(request, "op")? {
            "ping" => Ok(json!({"git": "gix"})),
            "state" => state(project, &strings(request, "specs")),
            "add" => add(project, &strings(request, "specs")),
            "rm_cached" => rm_cached(project, text(request, "spec")?),
            "ls_files" => ls_files(project, text(request, "spec")?),
            "check_ignore" => check_ignore(project, text(request, "path")?),
            "commit" => commit(
                project,
                text(request, "message")?,
                &strings(request, "specs"),
            ),
            "show_head" => show_head(project, text(request, "path")?),
            "pull" => pull(project, credentials_of(request)),
            "push" => push(project, credentials_of(request)),
            "continue" => rebase_continue(project),
            "abort" => rebase_abort(project),
            "stage_text" => {
                let n = request
                    .get("n")
                    .and_then(Value::as_u64)
                    .ok_or("the request has no `n`")?;
                stage_text(project, n as u8, text(request, "path")?)
            }
            "mark_resolved" => mark_resolved(project, text(request, "path")?),
            "config_get" => config_get(project, text(request, "key")?),
            "config_remove_section" => config_remove_section(
                project,
                text(request, "name")?,
                request.get("subsection").and_then(Value::as_str),
            ),
            "config_set" => config_set(project, text(request, "key")?, text(request, "value")?),
            "init" => init(project),
            "is_repo" => Ok(json!(Ctx::open(project).is_ok())),
            "rebasing" => Ok(json!({"rebasing": Ctx::open(project)?.rebasing()})),
            other => Err(format!("unknown op: {other}")),
        }
    })();
    match result {
        Ok(Value::Object(mut map)) => {
            map.insert("ok".into(), json!(true));
            Value::Object(map)
        }
        Ok(other) => json!({"ok": true, "value": other}),
        Err(message) => {
            let auth = needs_credentials(&message);
            json!({"ok": false, "error": message, "auth": auth})
        }
    }
}

/// The helper's whole life: read one JSON request on stdin, answer on stdout, exit. Shared by the
/// desktop executable (`--git-helper`) and the small `j2jme-git-helper` binary.
pub fn helper_main() -> ! {
    use std::io::Read;
    let mut input = String::new();
    let answer = match std::io::stdin().read_to_string(&mut input) {
        Ok(_) => match serde_json::from_str::<Value>(&input) {
            Ok(request) => run(&request),
            Err(e) => json!({"ok": false, "error": format!("not a request: {e}")}),
        },
        Err(e) => json!({"ok": false, "error": format!("cannot read the request: {e}")}),
    };
    println!("{answer}");
    std::process::exit(0)
}
