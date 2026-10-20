"""Toolkit-independent workbench command dispatch and availability contract."""
from dataclasses import dataclass
from typing import Callable
from .fuzzy_search import ranked

CONTRACT = 'spikes/commands/v1'


@dataclass(frozen=True)
class Context:
    page: str = 'Schematic'
    schematic: bool = True
    selected: int = 0
    undo: bool = False
    redo: bool = False
    busy: bool = False
    run_state: str = 'idle'
    interactive: bool = False
    has_results: bool = False
    wire_active: bool = False
    history_back: bool = False
    history_forward: bool = False


@dataclass(frozen=True)
class Command:
    id: str
    label: str
    handler: Callable
    description: str = ''


LABELS = {
    'view.component_maker': ('Component maker / user library…', 'Design symbols and pins, edit SPICE/C++/Verilog, and manage versioned source components.'),
    'edit.make_component': ('Make component from selected circuit…', 'Capture a portable source-backed subcircuit; opens the component maker without altering the circuit.'),
    'edit.make_subsheet_component': ('Make component from current subsheet…', 'Capture the actual subsheet definition and dependencies for reuse.'),
    'view.controller_boards': ('Controller board library…', 'Search sourced board pinouts, place labeled blocks and map sampled C/C++ I/O explicitly.'),
    'view.firmware': ('Firmware emulation…', 'Load approved Cortex-M binaries into an explicitly selected native Renode board model.'),
    'view.hierarchy': ('Schematic hierarchy…', 'Navigate actual native subcircuit instances and their declared port mappings.'),
    'view.flat_schematic': ('Flat schematic (all instances)', 'Return to the complete flattened source-backed schematic.'),
    'view.parent_sheet': ('Parent sheet', 'Go to the parent native subcircuit instance or flat view.'),
    'edit.net_label': ('Net label…', 'Attach a source-bound local/global/hierarchical label to a pin or wire.'),
    'view.wire_hops': ('Toggle wire hops', 'Optional curved bridges distinguish crossings of different actual nets.'),
    'view.code_canvas': ('Netlist beside schematic', 'Pair the live schematic with its syntax-highlighted netlist; select names to cross-probe.'),
    'view.code_canvas_top_bottom': ('Netlist above / below schematic', 'Use a top/bottom schematic and netlist split.'),
    'view.ide_canvas': ('C / HDL beside schematic', 'Pair the live schematic with the existing C/C++/Verilog/VHDL editor.'),
    'view.controller_canvas': ('Controller beside schematic', 'Pair sampled-controller settings/code with the live schematic.'),
    'view.controller_code_window': ('Attached controller code window', 'Open the same controller code in a small floating window linked to the block.'),
    'view.code_only': ('Code only — close schematic split', 'Return the live editor to its regular code page without discarding drafts.'),
    'view.back': ('Back', 'Return to the previous workspace or tool window without undoing circuit edits.'),
    'view.forward': ('Forward', 'Go to the next section in navigation history.'),
    'view.home': ('Home — schematic', 'Return to the main schematic, including from a split layout.'),
    'edit.canvas_text': ('Text / SPICE block…', 'T: enter a note or dot-prefixed directive block, validate it, then click to place it on the canvas.'),
    'edit.box_select': ('Select', 'Drag empty canvas to select an area. Ctrl adds to the selection; drag a selected symbol to move it.'),
    'edit.wire': ('Draw wire', 'Click a terminal to start; click corners and the destination terminal. Escape cancels.'),
    'edit.rotate': ('Rotate selection', 'Select a component first; rotate it by 90 degrees.'),
    'edit.duplicate': ('Duplicate selection', 'Preview an electrically isolated copy at the cursor; click repeatedly, rotate with Space, and finish with Escape.'),
    'edit.properties': ('Component properties', 'Select a component first; edit its values, models, pins and declared limits.'),
    'probe.voltage': ('Voltage probe', 'Click a terminal connection point to save a voltage probe. Run the circuit to acquire values.'),
    'view.component_catalog': ('Component catalog', 'Open the floating component selector; choose a part, review values, then click the schematic to place it.'),
    'view.fit_schematic': ('Fit schematic', 'Fit symbols, directives and attached plot cards into the live schematic canvas.'),
    'view.battery_laboratory': ('Battery laboratory', 'Open the prescribed-current battery study in a floating window.'),
    'view.monte_carlo': ('Monte Carlo', 'Open the linear reference Monte Carlo study in a floating window.'),
    'view.split_side_by_side': ('Split: schematic beside plots', 'Keep the live schematic and waveform panes side by side.'),
    'view.split_top_bottom': ('Split: schematic above plots', 'Keep the live schematic above the waveform panes.'),
    'view.insert_attached_plot': ('Insert attached mini plot', 'Click a pin or wire, then click to drop a saved waveform card with a matching-color attachment line.'),
    'view.fit': ('Fit active view', 'Fit the schematic or the active scientific plot.'),
    'view.net_navigator': ('Nets and pins…', 'Search electrical nets, highlight terminals and routes, cross-probe components and add voltage probes.'),
    'view.command_search': ('Find command…', 'Search all workbench commands and see why an action is unavailable.'),
    'view.offline_report': ('Interactive result report', 'Open an offline Plotly snapshot of actual acquired signals.'),
    'run.start': ('Run batch', 'Validate and run the selected circuit with the configured solver.'),
    'run.interactive': ('Start continuous', 'Start the native persistent session with bounded rolling capture.'),
    'run.pause': ('Pause / resume', 'Pause or resume a continuous session at accepted step boundaries.'),
    'run.stop': ('Stop simulation', 'Stop the current simulation worker.'),
    'edit.move': ('Move selection', 'Move selected symbols and calculate fresh attached-wire routes.'),
    'edit.drag': ('Drag selection', 'Move selected symbols while retaining nearby attached-wire bends.'),
    'edit.wire_bend': ('Flip wire bend posture', 'Switch the active wire preview between horizontal-first and vertical-first bends.'),
}

SELECTION = {'edit.properties', 'edit.properties_standard', 'edit.rotate', 'edit.move', 'edit.drag', 'edit.duplicate',
             'edit.rotate_standard', 'edit.mirror_horizontal', 'edit.mirror_vertical','edit.make_component'}
SCHEMATIC = SELECTION | {'edit.wire','edit.wire_bend','edit.box_select','edit.lasso_select','edit.select_all',
                        'edit.create_subsheet','edit.make_subsheet_component','probe.voltage','probe.differential','probe.current','probe.power','view.fit_schematic','edit.canvas_text','edit.net_label'}


def disabled_reason(command, context):
    if command in ('edit.make_component','edit.make_subsheet_component') and context.busy:return 'Stop active work before capturing components.'
    if command=='view.back' and not context.history_back:return 'No previous section.'
    if command=='view.forward' and not context.history_forward:return 'No next section.'
    if command in SCHEMATIC and not context.schematic:return 'Open the schematic or split schematic/plot view.'
    if command in SELECTION and not context.selected:return 'Select one or more components.'
    if command == 'edit.undo' and not context.undo:return 'Nothing to undo.'
    if command in ('edit.redo','edit.redo_alternative') and not context.redo:return 'Nothing to redo.'
    if command in ('run.start','run.interactive') and context.busy:return 'A simulation or build is already active.'
    if command == 'run.pause' and not (context.interactive and context.run_state in ('running','paused')):
        return 'Requires a running or paused continuous session.'
    if command == 'run.stop' and context.run_state not in ('starting','running','paused'):return 'No active simulation.'
    if command == 'view.fit' and context.page not in ('Schematic','Plots'):return 'Open a schematic or plot.'
    if command == 'view.offline_report' and not context.has_results:return 'Run a simulation or open acquired results first.'
    if command == 'edit.wire_bend' and not context.wire_active:return 'Start Wire before changing its bend posture.'
    return ''


class CommandRegistry:
    def __init__(self, context):
        self.context = context
        self.commands = {}

    def register(self, command):
        if command.id in self.commands:raise ValueError('Duplicate command: '+command.id)
        if not command.id or not command.label or not callable(command.handler):raise ValueError('Invalid command definition')
        self.commands[command.id] = command

    @classmethod
    def from_actions(cls, actions, context):
        registry = cls(context)
        for ident, handler in actions.items():
            label, description = LABELS.get(ident, (ident.split('.')[-1].replace('_',' ').capitalize(),''))
            registry.register(Command(ident,label,handler,description))
        return registry

    def reason(self, ident):
        if ident not in self.commands:raise ValueError('Unknown command: '+ident)
        return disabled_reason(ident,self.context())

    def execute(self, ident):
        reason = self.reason(ident)
        if reason:raise ValueError(reason)
        return self.commands[ident].handler()

    def search(self, query='', bindings=None):
        bindings=bindings or {}
        ordered=sorted(self.commands.values(),key=lambda command:(bool(self.reason(command.id)),command.label,command.id))
        commands=ranked(ordered,query,
                        text=lambda command:f'{command.id} {command.label} {command.description}')
        return [dict(id=command.id,label=command.label,description=command.description,
                     shortcut=bindings.get(command.id,''),disabled_reason=self.reason(command.id))
                for command in commands]
