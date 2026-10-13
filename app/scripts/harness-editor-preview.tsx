// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import HarnessDocumentEditor from "../src/HarnessDocumentEditor";
import fixture from "./fixtures/harness-editor.json";
import "../src/buttonStandard.css";

function Preview() {
  const [document, setDocument] = useState<Record<string, any>>(fixture);
  return <main style={{ maxWidth: 1320, margin: "auto", padding: 16 }}>
    <p>SPIKE harness editor visual acceptance fixture. Changes stay in this browser preview.</p>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      <a href="../assembly-performance-preview.html?harness=1">3D retained assembly and synthetic wiring</a>
    </div>
    <HarnessDocumentEditor value={document} onChange={setDocument} />
  </main>;
}

createRoot(document.getElementById("root")!).render(<Preview />);
