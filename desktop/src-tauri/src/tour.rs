//! The project the quick tutorial runs on (docs/IMPLEMENTATION_PLAN.md, M6.7). The tour never
//! touches the user's projects: it opens a fresh copy of the bundled `tour-project` in a
//! temporary folder, so a later "retour" starts from the original data, and deletes the copy
//! when done.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const PREFIX: &str = "j2jme-tour-";

/// Where the fixture is: `J2JME_TOUR_FIXTURE`, else next to the application, else the
/// development checkout.
pub fn fixture_dir() -> Option<PathBuf> {
    if let Ok(dir) = std::env::var("J2JME_TOUR_FIXTURE") {
        return Some(PathBuf::from(dir));
    }
    if let Some(bundled) = crate::bundle::dir().map(|dir| dir.join("tour-project")) {
        if bundled.join("mapper.toml").is_file() {
            return Some(bundled);
        }
    }
    let dev = Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures/tour-project");
    dev.join("mapper.toml")
        .is_file()
        .then(|| dev.canonicalize().unwrap_or(dev))
}

fn copy_dir(src: &Path, dst: &Path) -> io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let to = dst.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir(&entry.path(), &to)?;
        } else {
            fs::copy(entry.path(), to)?;
        }
    }
    Ok(())
}

/// Copies `fixture` to a new folder under `root` and returns it.
pub fn prepare_in(fixture: &Path, root: &Path) -> Result<PathBuf, String> {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let dst = root.join(format!("{PREFIX}{}-{nanos}", std::process::id()));
    copy_dir(fixture, &dst).map_err(|e| format!("cannot copy the tutorial project: {e}"))?;
    Ok(dst)
}

/// Deletes a copy made by `prepare_in`. Anything else is refused: this must never remove a
/// user's folder.
pub fn cleanup_in(path: &Path, root: &Path) -> Result<(), String> {
    let is_copy = path.parent() == Some(root)
        && path
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.starts_with(PREFIX));
    if !is_copy {
        return Err(format!("{} is not a tutorial project copy", path.display()));
    }
    match fs::remove_dir_all(path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

/// Removes the copies left by instances that no longer run (a crash). Only where `/proc`
/// tells whether a process is alive.
pub fn sweep_in(root: &Path) {
    if !Path::new("/proc").is_dir() {
        return;
    }
    let Ok(entries) = fs::read_dir(root) else { return };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        let Some(rest) = name.strip_prefix(PREFIX) else { continue };
        let Some(pid) = rest.split('-').next().and_then(|p| p.parse::<u32>().ok()) else { continue };
        if !Path::new("/proc").join(pid.to_string()).exists() {
            let _ = fs::remove_dir_all(entry.path());
        }
    }
}

pub fn prepare() -> Result<PathBuf, String> {
    let fixture = fixture_dir().ok_or("the tutorial project was not found")?;
    prepare_in(&fixture, &std::env::temp_dir())
}

pub fn cleanup(path: &Path) -> Result<(), String> {
    cleanup_in(path, &std::env::temp_dir())
}

pub fn sweep() {
    sweep_in(&std::env::temp_dir());
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("j2jme-tourtest-{}-{name}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn each_tour_gets_its_own_copy_and_the_original_stays_untouched() {
        let root = scratch("copy");
        let fixture = fixture_dir().expect("fixture");
        let a = prepare_in(&fixture, &root).unwrap();
        std::thread::sleep(std::time::Duration::from_millis(2));
        let b = prepare_in(&fixture, &root).unwrap();
        assert_ne!(a, b);
        assert!(a.join("mapper.toml").is_file() && a.join("tests/golden/orders").is_dir());
        assert!(a.join("fn/text.fn").is_file());
        // editing a copy does not reach the next one
        fs::write(a.join("mapper.toml"), "changed").unwrap();
        assert_ne!(fs::read_to_string(b.join("mapper.toml")).unwrap(), "changed");
        cleanup_in(&a, &root).unwrap();
        assert!(!a.exists() && b.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn only_a_copy_can_be_removed() {
        let root = scratch("guard");
        let mine = root.join("my-project");
        fs::create_dir_all(&mine).unwrap();
        assert!(cleanup_in(&mine, &root).is_err());
        assert!(cleanup_in(&root, &root).is_err());
        let nested = root.join(format!("{PREFIX}1-1")).join("inner");
        fs::create_dir_all(&nested).unwrap();
        assert!(cleanup_in(&nested, &root).is_err());
        assert!(mine.exists() && nested.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn a_crashed_instances_copy_is_swept_and_a_live_one_is_kept() {
        let root = scratch("sweep");
        let live = root.join(format!("{PREFIX}{}-1", std::process::id()));
        let dead = root.join(format!("{PREFIX}4294967295-1"));
        fs::create_dir_all(&live).unwrap();
        fs::create_dir_all(&dead).unwrap();
        sweep_in(&root);
        assert!(live.exists());
        if Path::new("/proc").is_dir() {
            assert!(!dead.exists());
        }
        let _ = fs::remove_dir_all(root);
    }
}
