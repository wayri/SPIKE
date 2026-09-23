import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import AppErrorBoundary from "./AppErrorBoundary";
import { DetachedToolWindowRoot, detachedToolKindFromLocation } from "./detachedToolWindows";
import "./styles.css";

const detachedTool = detachedToolKindFromLocation();
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><AppErrorBoundary>{detachedTool ? <DetachedToolWindowRoot kind={detachedTool} /> : <App />}</AppErrorBoundary></React.StrictMode>
);
