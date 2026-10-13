// SPDX-License-Identifier: Apache-2.0
import React from "react";
import { createRoot } from "react-dom/client";
import PwmElectrothermalPanel from "../src/PwmElectrothermalPanel";
import "../src/buttonStandard.css";
import "../src/styles.css";

createRoot(document.getElementById("root")!).render(<React.StrictMode><main style={{ padding: 12, maxWidth: 1000, margin: "0 auto", height: "100vh", overflowY: "auto", boxSizing: "border-box" }}>
  <h1>SPIKE PWM electrothermal reference</h1>
  <p>Native closed-loop behavioral buck. Winding-only thermal feedback; this is not a board-bound EMI study.</p>
  <a href="/">Open full SPIKE workbench</a>
  <PwmElectrothermalPanel workerAvailable />
</main></React.StrictMode>);
