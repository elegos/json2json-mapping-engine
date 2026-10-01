import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

ModuleRegistry.registerModules([AllCommunityModule]);

// Follow the system colour scheme (the grid theme reads this attribute).
const dark = window.matchMedia("(prefers-color-scheme: dark)");
const applyScheme = () => {
  document.body.dataset.agThemeMode = dark.matches ? "dark" : "light";
};
applyScheme();
dark.addEventListener("change", applyScheme);

// No <StrictMode>: in development it mounts, unmounts and mounts every component again, and the
// grid takes the unmounted cell editor for a finished edit and closes it at once.
createRoot(document.getElementById("root")!).render(<App />);
