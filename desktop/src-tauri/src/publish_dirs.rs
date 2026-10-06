//! A folder this user chose for a project: a path on this machine, so it lives in the app's
//! configuration folder, per project, and never in the project. Two of them: where `mapper
//! publish` writes (`[publish] dir` of `mapper.toml` is the project's own; this one beats it), and
//! where the build goes for a project in a synced folder (`J2JME_BUILD_DIR`).

use serde_json::{Map, Value};
use std::path::PathBuf;

/// Which choice: the name of its file in the app's configuration folder.
#[derive(Clone, Copy)]
pub struct Store(&'static str);

pub const PUBLISH: Store = Store("publish-dirs.json");
pub const BUILD: Store = Store("build-dirs.json");

fn file(dir: PathBuf, store: Store) -> PathBuf {
    dir.join(store.0)
}

fn load(path: &PathBuf) -> Map<String, Value> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .and_then(|v| if let Value::Object(map) = v { Some(map) } else { None })
        .unwrap_or_default()
}

/// The folder chosen for `project`. It need not exist yet: publishing creates it.
pub fn get(dir: PathBuf, store: Store, project: &str) -> Option<String> {
    let all = load(&file(dir, store));
    let path = all.get(project)?.as_str()?.to_string();
    (!path.is_empty()).then_some(path)
}

/// Remembers `path` for `project`; `None` goes back to the project's own setting.
pub fn set(dir: PathBuf, store: Store, project: &str, path: Option<String>) -> Result<(), String> {
    let target = file(dir.clone(), store);
    let mut all = load(&target);
    match path {
        Some(p) if !p.is_empty() => all.insert(project.to_string(), Value::String(p)),
        _ => all.remove(project),
    };
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let text = serde_json::to_string_pretty(&Value::Object(all)).map_err(|e| e.to_string())?;
    std::fs::write(target, text).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("j2jme-publish-dirs-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn remembered_per_project_and_forgotten() {
        let dir = scratch("a");
        assert_eq!(get(dir.clone(), PUBLISH, "/proj"), None);
        set(dir.clone(), PUBLISH, "/proj", Some("/srv/deploy/sql".into())).unwrap();
        set(dir.clone(), PUBLISH, "/other", Some("/srv/other".into())).unwrap();
        assert_eq!(get(dir.clone(), PUBLISH, "/proj"), Some("/srv/deploy/sql".into()));
        assert_eq!(get(dir.clone(), PUBLISH, "/other"), Some("/srv/other".into()));
        assert_eq!(get(dir.clone(), PUBLISH, "/elsewhere"), None);
        set(dir.clone(), PUBLISH, "/proj", None).unwrap();
        assert_eq!(get(dir.clone(), PUBLISH, "/proj"), None);
        assert_eq!(get(dir.clone(), PUBLISH, "/other"), Some("/srv/other".into()));
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn the_two_choices_do_not_meet() {
        let dir = scratch("c");
        set(dir.clone(), BUILD, "/proj", Some("/local/build".into())).unwrap();
        assert_eq!(get(dir.clone(), BUILD, "/proj"), Some("/local/build".into()));
        assert_eq!(get(dir.clone(), PUBLISH, "/proj"), None);
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn a_folder_that_does_not_exist_yet_is_kept() {
        let dir = scratch("b");
        set(dir.clone(), PUBLISH, "/proj", Some("/not/there/yet".into())).unwrap();
        assert_eq!(get(dir.clone(), PUBLISH, "/proj"), Some("/not/there/yet".into()));
        set(dir.clone(), PUBLISH, "/proj", Some(String::new())).unwrap(); // an empty path forgets it
        assert_eq!(get(dir.clone(), PUBLISH, "/proj"), None);
        let _ = std::fs::remove_dir_all(dir);
    }
}
