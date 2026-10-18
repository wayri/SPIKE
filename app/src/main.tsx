import PanelPopupQualification from "./PanelPopupQualification";
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
import "./PanelResponsive.css";
import "./WorkspaceHeader.css";
import AssemblyToolWindowRoot from "./AssemblyToolWindowRoot";
import { assemblyToolKindFromLocation } from "./assemblyToolWindows";
import ReportPreviewWindowRoot from "./ReportPreviewWindowRoot";
import { isReportPreviewLocation } from "./reportPreviewWindow";
import WorkspaceViewWindowRoot from "./WorkspaceViewWindowRoot";
import { workspaceViewIdFromLocation } from "./workspaceViewWindows";
import { installWebviewGuards } from "./webviewGuards";

installWebviewGuards(window, { allowDeveloperTools: import.meta.env.DEV });

const detachedTool = detachedToolKindFromLocation();
const assemblyTool = assemblyToolKindFromLocation();
const reportPreview = isReportPreviewLocation();
const workspaceView = workspaceViewIdFromLocation();
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><AppErrorBoundary>{new URLSearchParams(window.location.search).get("panelQualification") === "1" ? <PanelPopupQualification /> : isSchematicLocation() ? <SchematicWindowRoot /> : isAssistantWindow() ? <AssistantWindowRoot /> : reportPreview ? <ReportPreviewWindowRoot /> : assemblyTool ? <AssemblyToolWindowRoot kind={assemblyTool}/> : workspaceView ? <WorkspaceViewWindowRoot viewId={workspaceView}/> : detachedTool ? <DetachedToolWindowRoot kind={detachedTool} /> : <App />}</AppErrorBoundary></React.StrictMode>
);
