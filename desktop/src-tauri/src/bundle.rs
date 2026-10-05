//! Where the pieces shipped with the application live: `engine/` (the Python packages),
//! `python-runtime/` and `tour-project/`.
//!
//! It is the resource directory Tauri reports (next to the executable on Windows, under
//! `Contents/Resources` in a macOS bundle, `usr/lib/<name>` in an AppImage), set once at start.
//! Before that, or in a plain `cargo run`, it is the executable's own folder.

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

static RESOURCES: OnceLock<PathBuf> = OnceLock::new();

/// Windows hands out verbatim paths (`\\?\C:\…`); Python and its `PYTHONPATH` do not like them.
fn plain(dir: PathBuf) -> PathBuf {
    match dir.to_str().and_then(|s| s.strip_prefix(r"\\?\")) {
        Some(rest) => PathBuf::from(rest),
        None => dir,
    }
}

pub fn set(dir: PathBuf) {
    let _ = RESOURCES.set(plain(dir));
}

pub fn dir() -> Option<PathBuf> {
    if let Some(dir) = RESOURCES.get() {
        return Some(dir.clone());
    }
    std::env::current_exe()
        .ok()?
        .parent()
        .map(Path::to_path_buf)
}

#[cfg(test)]
mod tests {
    use super::plain;
    use std::path::PathBuf;

    #[test]
    fn a_verbatim_windows_prefix_is_dropped() {
        assert_eq!(
            plain(PathBuf::from(r"\\?\C:\Apps\J2JME")),
            PathBuf::from(r"C:\Apps\J2JME")
        );
        assert_eq!(plain(PathBuf::from("/opt/j2jme")), PathBuf::from("/opt/j2jme"));
    }
}
