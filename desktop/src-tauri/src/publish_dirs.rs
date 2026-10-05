//! The folder `mapper publish` writes to, chosen by this user for a project: a path on this
//! machine, so it lives in the app's configuration folder, per project, and never in the
//! project (`[publish] dir` of `mapper.toml` is the project's own; this one beats it).

use serde_json::{Map, Value};
use std::path::PathBuf;

fn file(dir: PathBuf) -> PathBuf {
    dir.join("publish-dirs.json")
}

fn load(path: &PathBuf) -> Map<String, Value> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .and_then(|v| if let Value::Object(map) = v { Some(map) } else { None })
        .unwrap_or_default()
}

/// The folder chosen for `project`. It need not exist yet: publishing creates it.
pub fn get(dir: PathBuf, project: &str) -> Option<String> {
    let all = load(&file(dir));
    let path = all.get(project)?.as_str()?.to_string();
    (!path.is_empty()).then_some(path)
}

/// Remembers `path` for `project`; `None` goes back to the project's own setting.
pub fn set(dir: PathBuf, project: &str, path: Option<String>) -> Result<(), String> {
    let target = file(dir.clone());
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
        assert_eq!(get(dir.clone(), "/proj"), None);
        set(dir.clone(), "/proj", Some("/srv/deploy/sql".into())).unwrap();
        set(dir.clone(), "/other", Some("/srv/other".into())).unwrap();
        assert_eq!(get(dir.clone(), "/proj"), Some("/srv/deploy/sql".into()));
        assert_eq!(get(dir.clone(), "/other"), Some("/srv/other".into()));
        assert_eq!(get(dir.clone(), "/elsewhere"), None);
        set(dir.clone(), "/proj", None).unwrap();
        assert_eq!(get(dir.clone(), "/proj"), None);
        assert_eq!(get(dir.clone(), "/other"), Some("/srv/other".into()));
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn a_folder_that_does_not_exist_yet_is_kept() {
        let dir = scratch("b");
        set(dir.clone(), "/proj", Some("/not/there/yet".into())).unwrap();
        assert_eq!(get(dir.clone(), "/proj"), Some("/not/there/yet".into()));
        set(dir.clone(), "/proj", Some(String::new())).unwrap(); // an empty path forgets it
        assert_eq!(get(dir.clone(), "/proj"), None);
        let _ = std::fs::remove_dir_all(dir);
    }
}
