// SPDX-License-Identifier: Apache-2.0
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import PythonWorkspace from "../../src/PythonWorkspace";
function Fixture() {
  const [theme, setTheme] = useState("professional-dark"), [open, setOpen] = useState(true);
  useEffect(() => { document.documentElement.dataset.tableTheme = theme; }, [theme]);
  return <><div id="fixture-bar"><b>Python IDE acceptance fixture</b><label>Theme <select aria-label="Fixture theme" value={theme} onChange={event => setTheme(event.target.value)}><option value="professional-dark">Dark</option><option value="light">Light</option><option value="high-contrast">High contrast</option></select></label>{!open && <button onClick={() => setOpen(true)}>Reopen IDE</button>}</div>{open && <PythonWorkspace design={null} results={null} onClose={() => setOpen(false)} onStatus={() => undefined} />}</>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
