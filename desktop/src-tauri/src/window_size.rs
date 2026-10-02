//! The window's size: a default big enough for the toolbar, remembered between runs, never
//! below a minimum and never above the space the screen offers (a smaller screen, another
//! monitor, a changed resolution: the saved size is fitted again on every start).

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tauri::{LogicalSize, Manager, WebviewWindow, WindowEvent};

/// Logical pixels (width, height).
type Size = (f64, f64);

pub const DEFAULT: Size = (1440.0, 900.0);
pub const MIN: Size = (1100.0, 640.0);
/// What a title bar and borders usually take, when the window cannot tell yet.
const DECORATION_GUESS: Size = (0.0, 40.0);

#[derive(Serialize, Deserialize)]
struct Saved {
    width: f64,
    height: f64,
}

/// The minimum size on a screen offering `available`: `MIN`, or the whole screen if smaller.
pub fn min_for(available: Size) -> Size {
    (MIN.0.min(available.0), MIN.1.min(available.1))
}

/// The size to open with: the saved one (else the default), at least the minimum, at most
/// `available`; the screen wins over the minimum.
pub fn fit(saved: Option<Size>, available: Size) -> Size {
    let (w, h) = saved
        .filter(|(w, h)| w.is_finite() && h.is_finite() && *w > 0.0 && *h > 0.0)
        .unwrap_or(DEFAULT);
    let (min_w, min_h) = min_for(available);
    (w.max(min_w).min(available.0), h.max(min_h).min(available.1))
}

fn file(window: &WebviewWindow) -> Option<PathBuf> {
    Some(window.app_handle().path().app_config_dir().ok()?.join("window-size.json"))
}

fn load(window: &WebviewWindow) -> Option<Size> {
    let text = std::fs::read_to_string(file(window)?).ok()?;
    let saved: Saved = serde_json::from_str(&text).ok()?;
    Some((saved.width, saved.height))
}

fn store(window: &WebviewWindow, size: Size) {
    let Some(path) = file(window) else { return };
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let saved = Saved { width: size.0, height: size.1 };
    if let Ok(text) = serde_json::to_string(&saved) {
        let _ = std::fs::write(path, text);
    }
}

/// The space the window can take, as the inner (content) size: the monitor's work area less
/// the window's decorations.
fn available(window: &WebviewWindow) -> Option<Size> {
    let monitor = window.current_monitor().ok().flatten().or_else(|| window.primary_monitor().ok().flatten())?;
    let scale = monitor.scale_factor();
    let area = monitor.work_area().size;
    let decoration = match (window.outer_size(), window.inner_size()) {
        (Ok(outer), Ok(inner)) if outer.height > inner.height => (
            (outer.width - inner.width.min(outer.width)) as f64 / scale,
            (outer.height - inner.height) as f64 / scale,
        ),
        _ => DECORATION_GUESS,
    };
    Some((area.width as f64 / scale - decoration.0, area.height as f64 / scale - decoration.1))
}

/// Sizes the window (it starts hidden), shows it, and saves its size when the user changes it.
pub fn setup(window: &WebviewWindow) {
    if let Some(space) = available(window) {
        let min = min_for(space);
        let _ = window.set_min_size(Some(LogicalSize::new(min.0, min.1)));
        let (w, h) = fit(load(window), space);
        let _ = window.set_size(LogicalSize::new(w, h));
    }
    let _ = window.show();

    // save a moment after the last resize, not on every step of a drag
    let generation = Arc::new(AtomicU64::new(0));
    let watched = window.clone();
    window.on_window_event(move |event| {
        if !matches!(event, WindowEvent::Resized(_)) {
            return;
        }
        let this = generation.fetch_add(1, Ordering::SeqCst) + 1;
        let (generation, window) = (generation.clone(), watched.clone());
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(500));
            if generation.load(Ordering::SeqCst) != this {
                return;
            }
            // a maximized window is the screen's size, not the one the user chose
            if window.is_maximized().unwrap_or(false)
                || window.is_fullscreen().unwrap_or(false)
                || window.is_minimized().unwrap_or(false)
            {
                return;
            }
            if let (Ok(inner), Ok(scale)) = (window.inner_size(), window.scale_factor()) {
                store(&window, (inner.width as f64 / scale, inner.height as f64 / scale));
            }
        });
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn first_run_uses_the_default() {
        assert_eq!(fit(None, (3840.0, 2000.0)), DEFAULT);
    }

    #[test]
    fn a_saved_size_is_kept_between_the_limits() {
        assert_eq!(fit(Some((1700.0, 950.0)), (2560.0, 1400.0)), (1700.0, 950.0));
    }

    #[test]
    fn never_below_the_minimum() {
        assert_eq!(fit(Some((300.0, 200.0)), (2560.0, 1400.0)), MIN);
    }

    #[test]
    fn never_above_the_available_space() {
        assert_eq!(fit(Some((2500.0, 1300.0)), (1920.0, 1040.0)), (1920.0, 1040.0));
        // the default itself does not fit a small screen
        assert_eq!(fit(None, (1366.0, 700.0)), (1366.0, 700.0));
    }

    #[test]
    fn a_screen_smaller_than_the_minimum_wins() {
        assert_eq!(fit(None, (1024.0, 600.0)), (1024.0, 600.0));
        assert_eq!(min_for((1024.0, 600.0)), (1024.0, 600.0));
    }

    #[test]
    fn garbage_in_the_file_means_the_default() {
        assert_eq!(fit(Some((f64::NAN, 500.0)), (3000.0, 2000.0)), DEFAULT);
        assert_eq!(fit(Some((-5.0, 500.0)), (3000.0, 2000.0)), DEFAULT);
    }
}
