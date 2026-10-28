import "highlight.js/styles/github-dark.css";
import "./style.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.querySelector<HTMLDivElement>("#app")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
