import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";

const wurzel = document.getElementById("wurzel");
if (!wurzel) throw new Error("Kein Element #wurzel im Dokument.");

createRoot(wurzel).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
