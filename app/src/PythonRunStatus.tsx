// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

export default function PythonRunStatus({ startedAt, name, stopping, timeoutSeconds }: { startedAt: number; name: string; stopping: boolean; timeoutSeconds: number }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const update = () => setElapsed(Math.max(0, (performance.now() - startedAt) / 1000));
    update(); const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return <div className="python-run-status">
    <div><strong role="status">{stopping ? "Stopping script…" : "Running script…"}</strong><span title={name}>{name}</span><time>{elapsed.toFixed(1)} s elapsed · {timeoutSeconds} s limit</time></div>
    <progress aria-label={stopping ? "Waiting for script cancellation" : "Script execution in progress"} aria-valuetext={`${elapsed.toFixed(1)} seconds elapsed; completion percentage unavailable`} />
    <small>Worker output appears when execution finishes.</small>
  </div>;
}
