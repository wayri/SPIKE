// SPDX-License-Identifier: Apache-2.0
import "./AssemblyIconToolbar.css";

export default function AssemblyViewportHelp() {
  return <section className="assembly-viewport-help" aria-label="Assembly viewport help">
    <h3>Assembly tools</h3>
    <p>Hover a tool for its full name. Tab focuses each control; Enter or Space activates it. A highlighted tool is enabled.</p>
    <h4>Navigate</h4>
    <p>Orbit: left drag. Pan: middle or right drag. Wheel zooms. Fit frames the visible assembly; Focus frames the selected board. Top and Isometric choose standard views.</p>
    <h4>Boards, layers and harnesses</h4>
    <p>Select a board occurrence before moving it, rotating it or changing its layers. Equal net names on separate boards do not connect them; use saved connector pin mappings. Select a visible cable to inspect its conductor.</p>
    <h4>Explode and section</h4>
    <p>Explode separates the display without changing physical placement or solver inputs. Sections clip the view; they do not remove material from a study. Clear cuts restores the complete display.</p>
    <h4>Headless commands</h4>
    <p>From the repository root, list supported project and assembly operations:</p>
    <code>python -m python.spike_cli --help</code>
    <code>python -m python.spike_cli --output update-result.json worker-call update-assembly.json --timeout-seconds 120</code>
    <p>The JSON request uses update_assembly_structure_in_project with the expected manifest digest and complete board, connector and harness lists. See docs/ASSEMBLY_CLI.md for a read, edit and save example.</p>
    <p>Reload the project after a CLI change. Camera, visibility, section and explode are display controls; the structure update command changes saved assembly data and does not run a solver.</p>
  </section>;
}
