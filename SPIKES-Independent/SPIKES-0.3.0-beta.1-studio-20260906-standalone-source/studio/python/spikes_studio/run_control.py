"""Owned-engine jobs. Batch isolation; cooperative, bounded interactive capture.

Interactive pause/stop acknowledge at native step boundaries, not hard realtime.
No GUI objects or callbacks are accessed from either worker.
"""
from collections import deque
import math
import multiprocessing as mp
import threading
import time


def native_batch(source, library, method='hybrid_trapezoidal'):
    """Bounded Cartesian sweep orchestration; every point is solved in C++."""
    from python.spikes.netlist import parse_netlist
    from python.spikes.native_runner import run_native_project
    from dataclasses import replace
    from python.spikes.runner import _measurements
    project=parse_netlist(source,native_extensions=True)
    variants=project.step_variants or (None,)
    # Limit retained Python/IPC data before solving, not after allocation.
    points=1
    if project.analysis.mode=='transient':
        points=int(project.analysis.stop_time_s/project.analysis.time_step_s)+2
    elif project.analysis.mode=='dc_sweep':
        points=int(abs((project.analysis.stop-project.analysis.start)/project.analysis.step))+2
    channels=1+len({n for e in project.elements for n in (e.positive_node,e.negative_node)})+2*len(project.elements)
    if project.steps and (len(variants)>128 or points*channels*len(variants)>2_000_000):
        raise ValueError('Sweep capture exceeds 128 runs or 2,000,000 retained scalar values; shorten the capture or reduce .step points')
    results=[]
    for index,variant in enumerate(variants):
        point=replace(project,elements=variant.elements if variant else project.elements,steps=(),step_variants=(),measurements=())
        result=run_native_project(point,library,integration_method=method).to_dict()
        result.setdefault('provenance',{}).update(step_index=index,step_parameters=dict(variant.parameters) if variant else {})
        if result['status']!='completed':return result
        if project.measurements:
            result['measurements']=_measurements(project,result['data'])
            result['provenance'].update(measurements=result['measurements'],measurement_processing='Python reduction of native recorded samples; AVG/RMS are sample-weighted, FIND is linearly interpolated')
        results.append(result)
    if not project.steps:return results[0]
    return {'status':'completed','data':{},'runs':results,'provenance':{'step_orchestration':'bounded sequential Cartesian; owned C++ per point','source_sha256':project.source_sha256},
            'measurements':{'by_step':[{'parameters':r['provenance']['step_parameters'],'measurements':r.get('measurements',{})} for r in results]}}


def _batch_worker(connection, source, library,method,kind,settings):
    try:
        if kind=='frequency':
            from .frequency import analyze
            connection.send(('result',analyze(source,settings)));return
        result=native_batch(source,library,method)
        connection.send(('result',result))
    except Exception as exc:
        connection.send(('error', str(exc)))
    finally:
        connection.close()


class BatchRun:
    """Run the unchanged fast batch path in a cancellable child process."""
    def __init__(self, source, library,*,method='hybrid_trapezoidal',kind='circuit',settings=None):
        context = mp.get_context('spawn')
        self.connection, child = context.Pipe(duplex=False)
        self.kind=kind
        self.process = context.Process(target=_batch_worker, args=(child, source, library,method,kind,settings), daemon=True)
        self.state, self.result, self.error = 'running', None, None
        self._response=None
        self.process.start()
        child.close()
        self.reader=threading.Thread(target=self._receive,daemon=True)
        self.reader.start()

    def _receive(self):
        # Large IPC results are received/unpickled off the GUI event loop.
        try:self._response=self.connection.recv()
        except (EOFError,OSError):self._response=('error','Native worker exited without a result')
        finally:self.connection.close()

    def poll(self):
        if self.state != 'running':
            return
        if self._response is not None:
            kind, value = self._response
            self._response=None
            if kind == 'result':
                self.result = value
                self.state = 'completed' if value.get('status') == 'completed' else 'failed'
                if self.state == 'failed': self.error = str(value.get('issues', value))
            else:
                self.state, self.error = 'failed', value
            self.process.join(timeout=.1)
            if self.process.is_alive(): self.process.terminate(); self.process.join(timeout=1)
        elif not self.process.is_alive() and not self.reader.is_alive():
            self.state, self.error = 'failed', f'Native worker exited: {self.process.exitcode}'
            self.process.join(timeout=.1)

    def stop(self):
        if self.state == 'running':
            self.process.terminate()
            self.process.join(timeout=2)
            self.state = 'stopped'


class InteractiveRun:
    """Persistent C++ DAE state, source controls and a latest-window ring.

    speed_ratio is simulated seconds per wall second. Timesteps remain those in
    .tran. Scheduling is best effort; GUI snapshots are coalesced, never queued.
    """
    def __init__(self, source, library, *, capacity=20000, speed_ratio=1.0,method='hybrid_trapezoidal',controller=None):
        from python.spikes.netlist import parse_netlist
        self.project = parse_netlist(source, native_extensions=True, transient_capture='rolling')
        if self.project.analysis.mode != 'transient':
            raise ValueError('Interactive mode requires .tran')
        if self.project.steps or self.project.measurements:
            raise ValueError('Interactive mode does not execute .step or .measure')
        if not isinstance(capacity, int) or not 2 <= capacity <= 200000:
            raise ValueError('Capture capacity must be 2..200000')
        if not math.isfinite(speed_ratio) or speed_ratio <= 0:
            raise ValueError('Speed ratio must be finite and positive')
        self.library, self.speed_ratio = library, speed_ratio
        self.controller=controller
        if controller is not None:controller.bind(self.project)
        if method not in ('hybrid_trapezoidal','backward_euler','bdf2'):raise ValueError('Unknown integration method')
        self.method=method
        self.controls = {e.name: e.value for e in self.project.elements
                         if e.kind in ('voltage_source', 'current_source') and e.waveform is None}
        if controller is not None:
            for pin in controller.outputs:self.controls.pop(pin['source'],None)
        self.condition = threading.Condition()
        self.state, self.error = 'starting', None
        self.pause_requested = self.stop_requested = False
        self.pending_controls = {}
        self.rows = deque(maxlen=capacity)
        self.total_samples = 0
        self.control_events = deque(maxlen=1000)
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def pause(self):
        with self.condition:
            if self.state not in ('running', 'starting'): raise ValueError('Run is not running')
            self.pause_requested = True
            self.condition.notify_all()

    def resume(self):
        with self.condition:
            if self.state != 'paused': raise ValueError('Run is not paused')
            self.pause_requested = False
            self.condition.notify_all()

    def stop(self):
        with self.condition:
            self.stop_requested = True
            self.condition.notify_all()

    def set_source(self, name, value):
        value = float(value)
        if name not in self.controls or not math.isfinite(value):
            raise ValueError('Choose an independent DC source and a finite SI value')
        with self.condition:
            if self.state not in ('starting', 'running', 'paused'): raise ValueError('Session is not active')
            self.pending_controls[name] = value
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            rows = list(self.rows)
            state, error = self.state, self.error
            total, events = self.total_samples, list(self.control_events)
        if not rows: return None
        return {'status': state, 'error': error, 'data': {
            'time_s': [r[0] for r in rows],
            **{table: {name: [r[i+1][j] for r in rows] for j, name in enumerate(names)}
               for i, (table, names) in enumerate(self.tables)}},
            'provenance': {'solver': 'SPIKES owned C++ persistent session',
                'owned_cpp_transient': True, 'integration': self.method,
                'source_sha256': self.project.source_sha256, 'library': str(self.library),
                'capture': 'rolling_window', 'total_samples': total,
                'dropped_samples': total-len(rows), 'control_events': events,
                'controller':None if self.controller is None else {'manifest_sha256':self.controller.manifest.manifest_sha256,'step_s':self.controller.config['step_s'],'semantics':'sampled feedback; zero-order held outputs; first tick after accepted plant point; trusted subprocess per tick'},
                'hard_real_time_qualified': False}}

    def _work(self):
        try:
            from python.spikes.native_abi import load_native_library
            from python.spikes.native_runner import _populate, _nodes
            library = load_native_library(self.library)
            names = tuple(e.name for e in self.project.elements)
            self.tables = [('node_voltage_v', _nodes(self.project)),
                           ('element_current_a', names), ('element_power_w', names)]
            with library.circuit() as circuit:
                _populate(circuit, self.project)
                with circuit.transient_session(
                    initialize_from_operating_point=not self.project.analysis.use_initial_conditions,
                    integration_method=self.method) as session:
                    def record():
                        row = (session.time_s,
                               tuple(session.node_voltage(n) for n in self.tables[0][1]),
                               tuple(session.element_current(n) for n in names),
                               tuple(session.element_power(n) for n in names))
                        with self.condition:
                            self.rows.append(row); self.total_samples += 1
                    deadline = time.monotonic()
                    while True:
                        with self.condition:
                            while self.pause_requested and not self.stop_requested:
                                self.state = 'paused'
                                self.condition.wait()
                                deadline = time.monotonic()
                            if self.stop_requested: break
                            self.state = 'running'
                            changes = self.pending_controls
                            self.pending_controls = {}
                        for name, value in changes.items():
                            session.set_source_value(name, value)
                            with self.condition:
                                self.control_events.append({'time_s': session.time_s, 'source': name, 'value': value})
                        step = self.project.analysis.time_step_s
                        if self.controller is not None:
                            changes=self.controller.advance(session)
                            with self.condition:
                                for name,value in changes.items():self.control_events.append({'time_s':session.time_s,'source':name,'value':value,'origin':'compiled_controller'})
                        if not session.step(step): raise RuntimeError(session.message)
                        record()
                        deadline += step / self.speed_ratio
                        with self.condition:
                            remaining = deadline-time.monotonic()
                            # Pacing waits are interruptible; do not pretend missed
                            # deadlines were met or attempt hardware synchronization.
                            while remaining > 0 and not self.stop_requested and not self.pause_requested:
                                self.condition.wait(timeout=remaining)
                                remaining = deadline-time.monotonic()
                    with self.condition: self.state = 'stopped'
        except Exception as exc:
            with self.condition: self.state, self.error = 'failed', str(exc)
