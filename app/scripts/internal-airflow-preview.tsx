// SPDX-License-Identifier: Apache-2.0
// Native visual acceptance entry: uses the real SPIKE worker, no mocked fields.
import React from "react";
import { createRoot } from "react-dom/client";
import InternalAirflowPanel from "../src/InternalAirflowPanel";
import type { InternalAirflowRequest } from "../src/InternalAirflowPanel";
import fixture from "./fixtures/internal-airflow-result.json";
import "../src/buttonStandard.css";
createRoot(document.getElementById("root")!).render(<main style={{ maxWidth: 1250, margin: "auto", padding: 16 }}><InternalAirflowPanel workerAvailable initialRequest={fixture.request as InternalAirflowRequest} initialResult={fixture.result} /></main>);
