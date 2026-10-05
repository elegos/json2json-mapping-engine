//! The name of the `.desktop` file an integrated AppImage runs from, used as the window's
//! application id (Linux).
//!
//! On Wayland a window cannot set its own icon: the compositor (KWin, Mutter) takes it from the
//! `.desktop` file whose id equals the window's `app_id`. GTK uses the program name for it, which
//! is `j2jme-desktop`, while whatever integrates the AppImage (Gear Lever, AppImageLauncher) names
//! the file its own way (`j2jme_desktop.desktop`, `appimagekit_<hash>-….desktop`). So, before GTK
//! starts, the program name becomes that file's id, when it can be found:
//! 1. `GIO_LAUNCHED_DESKTOP_FILE`, which the launchers set to the file they ran;
//! 2. else the file, among those the user has installed, that runs this `$APPIMAGE`.

use std::fs;
use std::path::{Path, PathBuf};

/// The id (the file name without `.desktop`) of the entry that launched this process.
pub fn id_for(appimage: Option<&str>, launched: Option<&str>, dirs: &[PathBuf]) -> Option<String> {
    if let Some(file) = launched.filter(|file| file.ends_with(".desktop")) {
        return stem(Path::new(file));
    }
    let appimage = appimage.filter(|path| !path.is_empty())?;
    for dir in dirs {
        let Ok(entries) = fs::read_dir(dir) else {
            continue;
        };
        let mut files: Vec<PathBuf> = entries.flatten().map(|entry| entry.path()).collect();
        files.sort();
        for file in files {
            if file.extension().is_some_and(|ext| ext == "desktop") && runs(&file, appimage) {
                return stem(&file);
            }
        }
    }
    None
}

fn stem(file: &Path) -> Option<String> {
    Some(file.file_stem()?.to_str()?.to_string())
}

/// Whether the `Exec` or `TryExec` of an entry names this AppImage.
fn runs(file: &Path, appimage: &str) -> bool {
    let Ok(text) = fs::read_to_string(file) else {
        return false;
    };
    text.lines().any(|line| {
        ["Exec=", "TryExec="]
            .iter()
            .any(|key| line.strip_prefix(key).is_some_and(|rest| rest.contains(appimage)))
    })
}

fn data_dirs() -> Vec<PathBuf> {
    let home = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| Path::new(&home).join(".local/share")));
    home.into_iter().map(|dir| dir.join("applications")).collect()
}

/// Sets the program name to the id of the entry this AppImage was launched from, if any.
/// Must run before GTK starts.
pub fn match_program_name() {
    let appimage = std::env::var("APPIMAGE").ok();
    let launched = std::env::var("GIO_LAUNCHED_DESKTOP_FILE").ok();
    if appimage.is_none() && launched.is_none() {
        return; // not an AppImage and not started from a menu: nothing to match
    }
    if let Some(id) = id_for(appimage.as_deref(), launched.as_deref(), &data_dirs()) {
        gtk::glib::set_prgname(Some(id.as_str()));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("j2jme-desktop-entry-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn the_launcher_names_the_file() {
        let id = id_for(None, Some("/home/u/.local/share/applications/j2jme_desktop.desktop"), &[]);
        assert_eq!(id.as_deref(), Some("j2jme_desktop"));
        // anything that is not a .desktop file is ignored
        assert_eq!(id_for(None, Some("/x/y"), &[]), None);
    }

    #[test]
    fn else_the_entry_that_runs_this_appimage_is_found() {
        let dir = scratch("find");
        fs::write(dir.join("other.desktop"), "[Desktop Entry]\nExec=env X=1 /apps/other.AppImage\n").unwrap();
        fs::write(
            dir.join("j2jme_desktop.desktop"),
            "[Desktop Entry]\nTryExec=/apps/j2jme.AppImage\nExec=env DESKTOPINTEGRATION=1 /apps/j2jme.AppImage\n",
        )
        .unwrap();
        let id = id_for(Some("/apps/j2jme.AppImage"), None, std::slice::from_ref(&dir));
        assert_eq!(id.as_deref(), Some("j2jme_desktop"));
        assert_eq!(id_for(Some("/apps/none.AppImage"), None, std::slice::from_ref(&dir)), None);
        assert_eq!(id_for(Some(""), None, &[dir.clone()]), None);
        let _ = fs::remove_dir_all(dir);
    }
}
