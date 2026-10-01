# Branding

- `logos.svg`: lossless reference sheet (favicon, app header, tray, monochrome). Do not edit by hand.
- `icon.svg`: the app icon, extracted clean (100x100 viewBox). Source of every PNG below.
- `icon-mono.svg`: monochrome variant, drawn with `currentColor`.

Generated (Inkscape / ImageMagick), regenerate after changing the SVGs:

| Output | Size | Use |
| --- | --- | --- |
| `ui/public/icon.svg` | vector | favicon and app header (copy of `icon.svg`) |
| `src-tauri/icons/icon.png` | 512 | Tauri window icon |
| `src-tauri/icons/128x128.png`, `128x128@2x.png`, `32x32.png` | 128 / 256 / 32 | Tauri bundle |
| `src-tauri/icons/icon.ico` | 16-256 | Windows |
| `src-tauri/icons/tray.png` | 32 | tray, colour |
| `src-tauri/icons/tray-mono.png`, `tray-mono@2x.png` | 32 / 64 | tray, monochrome (template image) |
