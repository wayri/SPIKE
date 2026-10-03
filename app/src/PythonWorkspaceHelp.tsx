// SPDX-License-Identifier: Apache-2.0
import "./PythonWorkspaceHelp.css";

export default function PythonWorkspaceHelp({ onTemplate }: { onTemplate?: (id: string) => void }) {
  const choose = (id: string) => onTemplate && <button type="button" onClick={() => onTemplate(id)}>Use template</button>;
  return <aside className="python-workspace-help" aria-label="Python workspace help">
    <h2>Python workspace help</h2>
    <p>Scripts run in a separate local Python process with the loaded design and selected result supplied through <code>spike</code>.</p>

    <section><h3>Files and tabs</h3>
      <p>The file tree shows scripts under the configured workspace root. Select a file to open it in another tab. <b>New</b> creates an untitled tab; <b>Open</b> adds an existing <code>.py</code> file without replacing another tab. Close removes a tab after checking for unsaved edits.</p>
      <p><b>Save</b> writes the current path. <b>Save as</b> chooses a new path. A dirty marker means the editor differs from the saved file. Closing a dirty tab or the workspace offers Save, Discard, and Cancel.</p>
      <p>The <b>+</b> button stays visible beside scrolling tabs. Each tab shows Draft, Unsaved, Saving, Saved, or Save failed. Use the arrow keys, Home, and End to navigate focused tabs.</p>
      <p><b>Backups</b> keeps bounded local recovery snapshots across restarts. Restore copy opens a separate unsaved tab. Save writes the script file; automatic backups and browser downloads do not establish a saved file.</p>
      <p><b>Files</b> shows open editors, recent workspace folders, and existing Git worktrees. Switching folders preserves each open file's own save path. Click the selected activity to hide its sidebar, or collapse Output and toggle the debugger Inspector to give the editor more room.</p>
    </section>

    <section><h3>Run and debug</h3>
      <p><b>Run</b> executes the active file with the selected time limit. <b>Debug</b> starts a supervised Python debug session. Click an editor gutter to add or remove a breakpoint. The debugger exposes the paused stack and bounded local-variable representations; it does not expand object properties.</p>
      <p>Use Continue to resume, Step over to run the current line, Step into to enter a call, and Step out to finish the current frame. Stop terminates the child session. Output and errors remain separate.</p>
    </section>

    <section><h3>Keyboard shortcuts</h3>
      <dl>
        <div><dt><kbd>Ctrl+S</kbd></dt><dd>Save</dd></div><div><dt><kbd>Ctrl+Shift+S</kbd></dt><dd>Save as</dd></div>
        <div><dt><kbd>Ctrl+O</kbd></dt><dd>Open</dd></div><div><dt><kbd>Ctrl+N</kbd></dt><dd>New</dd></div>
        <div><dt><kbd>Ctrl+W</kbd></dt><dd>Close tab</dd></div><div><dt><kbd>Ctrl+Enter</kbd></dt><dd>Run</dd></div>
        <div><dt><kbd>F5</kbd></dt><dd>Start or continue debugging</dd></div><div><dt><kbd>F9</kbd></dt><dd>Toggle breakpoint at cursor</dd></div>
        <div><dt><kbd>F10</kbd></dt><dd>Step over</dd></div>
        <div><dt><kbd>F11</kbd></dt><dd>Step into</dd></div><div><dt><kbd>Shift+F11</kbd></dt><dd>Step out</dd></div>
      </dl>
    </section>

    <section><h3>Workspace API</h3>
      <ul>
        <li><code>spike.design</code>: current normalized <code>spike/v1</code> design or <code>None</code>.</li>
        <li><code>spike.results</code>: selected result context or <code>None</code>. Check <code>complete</code> before reading <code>result</code>.</li>
        <li><code>spike.call(method, params)</code>: call a registered worker method through its normal validation contract.</li>
        <li><code>spike.extensions()</code>: inspect installed extensions, permissions, contributions, and trust.</li>
        <li><code>spike.invoke_extension(id, contribution, parameters)</code>: invoke an installed, session-trusted contribution.</li>
        <li><code>spike.publish_result(result)</code>: offer a complete design-bound AnalysisResult to the viewer.</li>
        <li><code>spike.publish_scalar_field(name, samples, ...)</code>: publish explicit finite samples for the loaded design.</li>
      </ul>
      {choose("hello-context")}{choose("design-summary")}{choose("result-overview")}
    </section>

    <section><h3>Analysis limits</h3>
      <p>Templates labeled setup or draft do not launch an analysis. Fill every required value and use the documented preflight for the selected solver. A registered solver or successful capability probe does not establish runtime availability, convergence, or physical validation.</p>
      <p>DC, AC, circuit, SI, thermal, EMI screening, extension, and reduced multiboard paths retain the status and limitations returned by their workers. Eye diagrams need a supported channel plus explicit timing and endpoint models. Independent board batches do not establish coupled assembly physics.</p>
      <p>Internal tetra meshing and focused PCB volume preparation are experimental. Imported external fields retain their upstream qualification. EM samples, contours, radiation views, and EMI screening are not full-wave or compliance qualification.</p>
    </section>

    <section><h3>Local execution</h3>
      <p>The child process is a cancellation and stability boundary, not a security sandbox. Scripts have local file and installed-package access. A saved script runs from its parent folder; an unsaved tab runs from the selected workspace folder. Use explicit paths, bounded data, finite JSON values, and a timeout. The editor limits code to 512 KB; output and result payloads are also bounded.</p>
      {choose("working-directory")}{choose("worker-capabilities")}
    </section>
  </aside>;
}
