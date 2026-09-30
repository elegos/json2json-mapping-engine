import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import { StrictMode } from "react";
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

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
