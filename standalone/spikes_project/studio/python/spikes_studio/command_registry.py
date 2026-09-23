"""Toolkit-independent workbench command dispatch and availability contract."""
from dataclasses import dataclass
from typing import Callable

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


@dataclass(frozen=True)
class Command:
    id: str
    label: str
    handler: Callable
    description: str = ''


LABELS = {
    'view.fit': ('Fit active view', 'Fit the schematic or the active scientific plot.'),
    'view.command_search': ('Find command…', 'Search all workbench commands and see why an action is unavailable.'),
    'view.offline_report': ('Interactive result report', 'Open an offline Plotly snapshot of actual acquired signals.'),
    'run.start': ('Run batch', 'Validate and run the selected circuit with the configured solver.'),
    'run.interactive': ('Start continuous', 'Start the native persistent session with bounded rolling capture.'),
    'run.pause': ('Pause / resume', 'Pause or resume a continuous session at accepted step boundaries.'),
    'run.stop': ('Stop simulation', 'Stop the current simulation worker.'),
}

SELECTION = {'edit.properties', 'edit.properties_standard', 'edit.rotate',
             'edit.rotate_standard', 'edit.mirror_horizontal', 'edit.mirror_vertical'}
SCHEMATIC = SELECTION | {'edit.wire','edit.box_select','edit.lasso_select','edit.select_all',
                        'edit.create_subsheet','probe.voltage','probe.differential','probe.current','probe.power'}


def disabled_reason(command, context):
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
        terms=query.casefold().split();bindings=bindings or {};rows=[]
        for ident,command in self.commands.items():
            haystack=f'{ident} {command.label} {command.description}'.casefold()
            if all(term in haystack for term in terms):
                rows.append(dict(id=ident,label=command.label,description=command.description,
                                 shortcut=bindings.get(ident,''),disabled_reason=self.reason(ident)))
        return sorted(rows,key=lambda row:(bool(row['disabled_reason']),row['label'],row['id']))
