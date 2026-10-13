import React from "react";
import AssistantWindowRoot from "./AssistantWindowRoot";
import { isAssistantWindow } from "./assistantWindow";
import ReactDOM from "react-dom/client";
import App from "./App";
import SchematicWindowRoot from "./SchematicWindowRoot";
import { isSchematicLocation } from "./schematicWindow";
import AppErrorBoundary from "./AppErrorBoundary";
import { DetachedToolWindowRoot, detachedToolKindFromLocation } from "./detachedToolWindows";
import "./styles.css";
import "./buttonStandard.css";
import "./WorkbenchChrome.css";
import "./FocusWorkspace.css";
import AssemblyToolWindowRoot from "./AssemblyToolWindowRoot";
import { assemblyToolKindFromLocation } from "./assemblyToolWindows";
import ReportPreviewWindowRoot from "./ReportPreviewWindowRoot";
import { isReportPreviewLocation } from "./reportPreviewWindow";
import { installWebviewGuards } from "./webviewGuards";

installWebviewGuards(window, { allowDeveloperTools: import.meta.env.DEV });

const detachedTool = detachedToolKindFromLocation();
const assemblyTool = assemblyToolKindFromLocation();
const reportPreview = isReportPreviewLocation();
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><AppErrorBoundary>{isSchematicLocation() ? <SchematicWindowRoot /> : isAssistantWindow() ? <AssistantWindowRoot /> : reportPreview ? <ReportPreviewWindowRoot /> : assemblyTool ? <AssemblyToolWindowRoot kind={assemblyTool}/> : detachedTool ? <DetachedToolWindowRoot kind={detachedTool} /> : <App />}</AppErrorBoundary></React.StrictMode>
);
