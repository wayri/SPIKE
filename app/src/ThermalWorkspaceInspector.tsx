// SPDX-License-Identifier: Apache-2.0
import React from "react";

/** Domain-specific landing panel; opening results never schedules a solver. */
export default function ThermalWorkspaceInspector({ hasResult, onSetup, onResults }: {
  hasResult: boolean;
  onSetup: () => void;
  onResults: () => void;
}) {
  return <div className="inspector shared-mesh-inspector" aria-label="Thermal study controls">
    <div className="setup-block">
      <label>THERMAL STUDY</label>
      <b>{hasResult ? "Retained thermal results" : "Thermal setup"}</b>
      <small>{hasResult
        ? "The saved temperature field is shown on the board. Use Play for available transient frames. Opening a result does not run a simulation."
        : "Configure heat sources, materials, contacts and cooling before running a thermal study."}</small>
      <button type="button" className="secondary-btn" onClick={onSetup}>Configure thermal study</button>
      <button type="button" className="secondary-btn" disabled={!hasResult} onClick={onResults}>Review saved thermal results</button>
      <small>Coverage and numerical limitations are retained with each result. Missing package or underside fields are not inferred.</small>
    </div>
  </div>;
}
