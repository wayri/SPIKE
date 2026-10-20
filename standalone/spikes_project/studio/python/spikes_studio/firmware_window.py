# SPDX-License-Identifier: Apache-2.0
"""Floating, explicit firmware-emulation controls for admitted Cortex-M boards."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import weakref
import wx,wx.grid
from .controller_boards import get_record
from .firmware_image import TARGETS,inspect_image
from .firmware_session import FirmwareSession,gpio_pin
from .renode_process import find_runtime,runtime_digest
LIMITS = (
    "Functional Renode instruction emulation; native electrical pads are generic/unqualified. "
    "Timestamped mode captures software GPIO only, with held inputs—not cycle-accurate or qualified SI/PI, ADC, real-time or HIL. The emulator "
    "executes with your user permissions; process isolation is not a hostile-code sandbox."
)
_WINDOWS: "weakref.WeakKeyDictionary[wx.Window, FirmwareWindow]" = weakref.WeakKeyDictionary()
def _target_from_block(block):
    if block is None:
        return next(iter(TARGETS))
    target = block.get("board", {}).get("id")
    if target not in TARGETS:
        raise ValueError(f"unsupported firmware target: {target}")
    return target
def _engineering_seconds(text):
    from python.spikes.netlist import parse_spice_number
    value = parse_spice_number(text.strip(), "time")
    if not 1e-9 <= value <= 1:
        raise ValueError("Step duration must be 1 ns..1 s")
    nanoseconds = round(value * 1e9)
    if abs(nanoseconds / 1e9 - value) > 1e-15:
        raise ValueError("Step duration must be an integer number of nanoseconds")
    return nanoseconds / 1e9
class FirmwareWindow(wx.Frame):
    """Reusable manager; all native session access is serialized off the UI thread."""
    def __init__(self, owner, block=None):
        target = _target_from_block(block)
        super().__init__(owner, title="SPIKES firmware manager", size=(1000, 760),
                         style=wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT)
        if owner.GetIcon().IsOk():self.SetIcon(owner.GetIcon())
        self.owner=owner;self.block=block;self.closed=False;self.busy=False;self.running=False
        if hasattr(owner,'palette'):self.palette=owner.palette
        self.generation=0;self.session=None;self.inspected=None;self.approval=None;self.inputs={};self.pending=None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spikes-firmware")
        self.records=[get_record(target_id) for target_id in TARGETS];self.target_ids=list(TARGETS)
        self._build(target)
        self.timer=wx.Timer(self);self.Bind(wx.EVT_TIMER,self._timer,self.timer);self.timer.Start(100)
        self.Bind(wx.EVT_CLOSE,self.close);self.Bind(wx.EVT_WINDOW_DESTROY,self._destroyed);self.Show()
    def _build(self, selected_target):
        panel=wx.Panel(self);outer=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(outer)
        note=wx.StaticText(panel,label=LIMITS);note.Wrap(940);outer.Add(note,0,wx.EXPAND|wx.ALL,8)
        setup=wx.FlexGridSizer(cols=3,hgap=7,vgap=7);setup.AddGrowableCol(1,1)
        self.target = wx.Choice(panel, choices=[f"{r['name']} - {r['revision']}" for r in self.records])
        self.target.SetSelection(self.target_ids.index(selected_target))
        runtime=find_runtime()
        self.runtime = wx.FilePickerCtrl(panel, path=str(runtime or ""),
            message="Select reviewed Renode 1.17.0 executable", wildcard="Executable (*.exe)|*.exe")
        self.image = wx.FilePickerCtrl(panel, message="Select Cortex-M firmware",
            wildcard="Firmware (*.elf;*.bin)|*.elf;*.bin|ELF (*.elf)|*.elf|Raw binary (*.bin)|*.bin")
        for label, control in (("Board target", self.target), ("Renode runtime", self.runtime),
                               ("Firmware image", self.image)):
            setup.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            setup.Add(control, 1, wx.EXPAND)
            setup.Add((1, 1))
        outer.Add(setup, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        approval=wx.WrapSizer(wx.HORIZONTAL);self.inspect_button=wx.Button(panel,label="Inspect firmware")
        self.trust=wx.CheckBox(panel,label="Trust this inspected hash and reviewed runtime")
        self.load_button=wx.Button(panel,label="Load trusted firmware");self.help_button=wx.Button(panel,label="Help")
        example=wx.Button(panel,label='Example firmware');example.Bind(wx.EVT_BUTTON,self.example)
        approval.Add(example,0,wx.ALL,4)
        for control in (self.inspect_button, self.trust, self.load_button, self.help_button):
            approval.Add(control, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        outer.Add(approval, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        self.metadata = wx.TextCtrl(panel, style=wx.TE_READONLY)
        outer.Add(self.metadata, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        actions=wx.BoxSizer(wx.HORIZONTAL)
        actions.Add(wx.StaticText(panel, label="Step duration"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.duration = wx.TextCtrl(panel, value="100u", size=(90, -1))
        self.step_button=wx.Button(panel,label="Step");self.run_button=wx.Button(panel,label="Run")
        self.reset_button=wx.Button(panel,label="Reset / reload");self.stop_button=wx.Button(panel,label="Stop")
        self.circuit_button=wx.Button(panel,label="Run with circuit")
        for control in (self.duration, self.step_button, self.run_button,
                        self.reset_button, self.stop_button, self.circuit_button):
            actions.Add(control, 0, wx.ALL, 4)
        self.status=wx.StaticText(panel,label="Stopped - inspect an image to begin")
        actions.Add(self.status, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 7)
        outer.Add(actions, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        from .firmware_pin_workflow import build
        build(self,panel,outer)
        self.gpio=wx.grid.Grid(panel);self.gpio.CreateGrid(0,5)
        for col, (label, width) in enumerate((("Physical pin", 230), ("MCU GPIO", 90),
                                               ("Firmware mode", 120), ("Sampled level", 105),
                                               ("Drive DI", 75))):
            self.gpio.SetColLabelValue(col,label);self.gpio.SetColSize(col,width)
        self.gpio.SetRowLabelSize(0);outer.Add(self.gpio,1,wx.EXPAND|wx.ALL,8)
        uart_box=wx.StaticBoxSizer(wx.VERTICAL,panel,"UART (bounded byte stream)")
        self.uart_rx = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 105))
        uart_box.Add(self.uart_rx, 1, wx.EXPAND | wx.ALL, 4)
        uart_row=wx.BoxSizer(wx.HORIZONTAL);self.uart_tx=wx.TextCtrl(panel);self.uart_send=wx.Button(panel,label="Send UTF-8")
        uart_row.Add(self.uart_tx, 1, wx.EXPAND | wx.ALL, 4)
        uart_row.Add(self.uart_send, 0, wx.ALL, 4)
        uart_box.Add(uart_row, 0, wx.EXPAND)
        outer.Add(uart_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        for control,event,handler in ((self.target,wx.EVT_CHOICE,self._configuration_changed),
            (self.runtime,wx.EVT_FILEPICKER_CHANGED,self._configuration_changed),(self.image,wx.EVT_FILEPICKER_CHANGED,self._configuration_changed),
            (self.trust,wx.EVT_CHECKBOX,self._trust_changed),(self.inspect_button,wx.EVT_BUTTON,self.inspect),
            (self.load_button,wx.EVT_BUTTON,self.load),(self.help_button,wx.EVT_BUTTON,self.help),(self.step_button,wx.EVT_BUTTON,self.step),
            (self.run_button,wx.EVT_BUTTON,self.toggle_run),(self.reset_button,wx.EVT_BUTTON,self.reset),
            (self.stop_button,wx.EVT_BUTTON,self.stop),(self.circuit_button,wx.EVT_BUTTON,self.run_with_circuit),
            (self.uart_send,wx.EVT_BUTTON,self.send_uart)):
            control.Bind(event,handler)
        self.gpio.Bind(wx.grid.EVT_GRID_CELL_CHANGED,self._gpio_changed)
        self.SetMinSize((820, 620))
        self._populate_pins()
        self._reflect()
        if hasattr(self.owner,"palette"):
            from .themes import apply_window
            apply_window(self,self.owner.palette)
    @property
    def target_id(self):
        return self.target_ids[self.target.GetSelection()]
    def select_block(self, block):
        target=_target_from_block(block);self.block=block
        from .firmware_pin_workflow import MODES
        self.coupling_mode.SetSelection(MODES.index(block.get('firmware_coupling_mode','legacy')))
        self.target.SetSelection(self.target_ids.index(target));self._configuration_changed()
    def attachment_context(self):
        """Return explicit data for a later circuit-coupling confirmation flow."""
        return {"block": self.block, "target_id": self.target_id,
                "firmware": dict(self.inspected) if self.inspected else None,
                "runtime_path": self.runtime.GetPath(),
                "approved": bool(self.approval and self.trust.GetValue()),
                "session": self.session}
    def help(self, event=None):
        opener=getattr(self.owner,"open_help_file",None)
        if opener:
            opener("CONTROLLER_FIRMWARE.md")
        else:
            self.status.SetLabel("Firmware help is unavailable in this host")
    def example(self,event=None):
        from .help_center import example_dir
        name='stm32f407_gpio_echo.bin' if self.target_id=='st-stm32f407g-disc1-mb997' else 'nrf52840_gpio_echo.bin'
        self.image.SetPath(str(example_dir().parent/'controller_firmware'/name));self._configuration_changed()
    def _configuration_changed(self, event=None):
        pending=self.pending if self.busy else None;self.generation+=1;generation=self.generation;self.running=False
        self.trust.SetValue(False);self.approval=None;self.inspected=None;self.inputs.clear()
        self.metadata.SetValue("")
        self._populate_pins()
        if self.session is not None:
            self.stop()
        elif pending is not None:
            self.status.SetLabel("Selection changed - discarding pending operation...")
            pending.add_done_callback(lambda task:wx.CallAfter(self._configuration_settled,generation))
        else:
            self.busy=False
            self.status.SetLabel("Configuration changed - inspect and approve again")
            self._reflect()
    def _configuration_settled(self,generation):
        if not self._live(generation):return
        self.busy=False;self.pending=None;self.status.SetLabel("Configuration changed - inspect and approve again");self._reflect()
    def _populate_pins(self):
        count=self.gpio.GetNumberRows()
        if count:
            self.gpio.DeleteRows(0, count)
        self.pin_rows=[];record=self.records[self.target.GetSelection()]
        for pin in record["pins"]:
            try:
                port,index=gpio_pin(self.target_id,pin)
            except ValueError:
                continue
            self.pin_rows.append((pin,port,index))
        if self.pin_rows:
            self.gpio.AppendRows(len(self.pin_rows))
        for row, (pin, port, index) in enumerate(self.pin_rows):
            self.gpio.SetCellValue(row, 0, f"{pin['header']}.{pin['position']}  {pin['label']}")
            self.gpio.SetCellValue(row, 1, f"P{port}.{index}")
            self.gpio.SetCellValue(row, 2, "not sampled")
            self.gpio.SetCellValue(row, 3, "-")
            for col in range(4):
                self.gpio.SetReadOnly(row, col)
            self.gpio.SetCellRenderer(row, 4, wx.grid.GridCellBoolRenderer())
            self.gpio.SetCellEditor(row, 4, wx.grid.GridCellBoolEditor())
            self.gpio.SetCellValue(row, 4, "1" if self.inputs.get((port, index), False) else "")
    def _trust_changed(self, event=None):
        if not self.trust.GetValue():
            self.approval = None
        elif not self.inspected:
            self.trust.SetValue(False)
            self.status.SetLabel("Inspect the selected firmware before approval")
        else:
            try:
                runtime_digest(self.runtime.GetPath())
                self.approval = (self.target_id, self.image.GetPath(), self.runtime.GetPath(),
                                 self.inspected["sha256"])
                self.status.SetLabel("Exact firmware hash and reviewed runtime approved")
            except Exception as error:
                self.trust.SetValue(False)
                self.approval=None
                self.status.SetLabel(f"Approval failed: {error}")
        self._reflect()
    def inspect(self, event=None):
        if self.busy:
            return
        target,path=self.target_id,self.image.GetPath()
        if not path:
            self.status.SetLabel("Select a .elf or .bin firmware image")
            return
        self.trust.SetValue(False);self.approval=None
        self.status.SetLabel("Inspecting bytes without execution...")
        def complete(info):
            if target != self.target_id or path != self.image.GetPath():
                self.status.SetLabel("Selection changed; inspect again")
                return
            self.inspected = info
            self.metadata.SetValue(
                f"{info['kind'].upper()} | {info['size']} bytes | SHA-256 {info['sha256']} | "
                f"reset 0x{info['reset_pc']:08x} | SP 0x{info['initial_sp']:08x}")
            self.status.SetLabel("Inspection complete; no firmware was executed")
        self._submit(lambda: inspect_image(path, target), complete)
    def load(self, event=None):
        if self.busy:
            return
        expected = (self.target_id, self.image.GetPath(), self.runtime.GetPath(),
                    self.inspected["sha256"] if self.inspected else None)
        if not self.trust.GetValue() or self.approval != expected:
            self.status.SetLabel("Inspect and explicitly approve this exact firmware/runtime first")
            return
        if getattr(self.owner, "job_running", False):
            self.status.SetLabel("Stop the active circuit job before loading firmware")
            return
        old=self.session;self.session=None;self.running=False;self.inputs.clear();self._populate_pins()
        self.status.SetLabel("Starting reviewed native runtime in background...")
        def work():
            if old:
                old.close()
            return FirmwareSession(expected[2], expected[1], expected[0], trusted=True,
                                   expected_sha256=expected[3])
        def complete(session):
            self.session=session
            self.uart_rx.SetValue("")
            self.status.SetLabel("Loaded - virtual time 0 s")
            self._request_snapshot()
        self._submit(work, complete, fatal=True)
    def step(self, event=None):
        if self.busy or not self.session:
            return
        try:
            seconds=_engineering_seconds(self.duration.GetValue())
        except ValueError as error:
            self.status.SetLabel(str(error))
            return
        session=self.session
        self.status.SetLabel("Advancing bounded virtual time...")
        self._submit(lambda: self._advance(session, seconds), self._accept_snapshot, fatal=True)
    def toggle_run(self, event=None):
        if not self.session:
            self.status.SetLabel("Load trusted firmware before running")
            return
        self.running = not self.running
        self.run_button.SetLabel("Pause" if self.running else "Run")
        if not self.running:
            self.status.SetLabel(f"Paused - virtual time {self.session.time_s:.9g} s")
    def reset(self, event=None):
        if self.session and not self.busy:
            self.load()
    def stop(self, event=None):
        self.running = False
        self.run_button.SetLabel("Run")
        session = self.session
        self.session = None
        self.generation += 1
        self.busy = True
        self.status.SetLabel("Stopping runtime in background...")
        future = self.executor.submit(lambda: session.close() if session else None)
        future.add_done_callback(lambda task, gen=self.generation: wx.CallAfter(self._stopped, gen, task))
        self._reflect()
    def _stopped(self, generation, future):
        if not self._live(generation):
            return
        self.busy = False
        try:
            future.result()
            self.status.SetLabel("Stopped")
        except Exception as error:
            self.status.SetLabel(f"Stop failed: {error}")
        self._reflect()
    def _timer(self, event=None):
        if self.running and self.session and not self.busy:
            self.step()
    def _advance(self, session, seconds):
        try:
            session.run_for(seconds)
            return self._snapshot(session)
        except BaseException:
            session.close()
            raise
    def _snapshot(self, session):
        ports = {port for _pin, port, _index in self.pin_rows}
        states = {port: session.gpio_state(port) for port in ports}
        return session.time_s, states, session.uart_read()
    def _request_snapshot(self):
        if self.session and not self.busy:
            session = self.session
            self._submit(lambda:self._safe_snapshot(session),self._accept_snapshot,fatal=True)
    def _safe_snapshot(self,session):
        try:return self._snapshot(session)
        except BaseException:session.close();raise
    def _accept_snapshot(self, result):
        time_s, states, uart = result
        for row, (_pin, port, index) in enumerate(self.pin_rows):
            state = states[port]
            if "mode" in state:
                mode = (state["mode"] >> (index * 2)) & 3
                mode_name = ("input", "output", "alternate", "analog")[mode]
            else:
                mode_name = "output" if state["direction"] & (1 << index) else "input"
            sampled = state["output"] if mode_name == "output" else state["input"]
            self.gpio.SetCellValue(row, 2, mode_name)
            self.gpio.SetCellValue(row, 3, "High" if sampled & (1 << index) else "Low")
        if uart:
            text = self.uart_rx.GetValue() + uart.decode("utf-8", errors="replace")
            self.uart_rx.SetValue(text[-65536:])
            self.uart_rx.SetInsertionPointEnd()
        self.status.SetLabel(f"{'Running' if self.running else 'Paused'} - virtual time {time_s:.9g} s")
    def _gpio_changed(self, event):
        row, col = event.GetRow(), event.GetCol()
        if col != 4 or not self.session or self.busy:
            event.Skip()
            return
        _pin, port, index = self.pin_rows[row]
        level = self.gpio.GetCellValue(row, 4) == "1"
        self.inputs[(port, index)] = level
        session = self.session
        self._submit(lambda: self._set_gpio(session, port, index, level), self._accept_snapshot,
                     fatal=True)
    def _set_gpio(self, session, port, index, level):
        try:
            session.set_gpio(port, index, level)
            return self._snapshot(session)
        except BaseException:
            session.close()
            raise
    def send_uart(self, event=None):
        if self.busy or not self.session:
            return
        data = self.uart_tx.GetValue().encode("utf-8")
        if len(data) > 256:
            self.status.SetLabel("UART injection is limited to 256 UTF-8 bytes")
            return
        session = self.session
        self._submit(lambda: self._send_uart(session, data), self._accept_snapshot, fatal=True)
    def run_with_circuit(self,event=None):
        from .firmware_coupling import run
        run(self.owner,self)
    def _send_uart(self, session, data):
        try:
            session.uart_send(data)
            return self._snapshot(session)
        except BaseException:
            session.close()
            raise
    def _submit(self, work, complete, fatal=False):
        self.busy = True
        generation = self.generation
        self._reflect()
        future=self.executor.submit(work);self.pending=future
        future.add_done_callback(lambda task:self._dispatch(generation,task,complete,fatal))
    def _dispatch(self,generation,future,complete,fatal):
        if self.closed:return  # close() already queued worker-side cleanup before executor shutdown.
        if generation!=self.generation:self._discard_result(future);return
        wx.CallAfter(self._finish,generation,future,complete,fatal)
    def _finish(self, generation, future, complete, fatal):
        if not self._live(generation):
            if not self.closed:self.executor.submit(self._discard_result,future)
            return
        self.busy=False
        if self.pending is future:self.pending=None
        try:
            complete(future.result())
        except Exception as error:
            self.running = False
            self.run_button.SetLabel("Run")
            if fatal:
                self.session = None
            self.status.SetLabel(f"Firmware operation failed: {error}")
        self._reflect()
    @staticmethod
    def _discard_result(future):
        try:
            result = future.result()
            if hasattr(result,'close'):
                result.close()
        except BaseException:
            pass
    def _reflect(self):
        active = self.session is not None
        editable=not self.busy and self.block is not None and not getattr(self.owner,'job_running',False)
        self.pad_properties_button.Enable(editable);self.coupling_mode.Enable(editable)
        for row in range(self.gpio.GetNumberRows()):
            self.gpio.SetReadOnly(row, 4, not active or self.busy)
        self.inspect_button.Enable(not self.busy)
        self.load_button.Enable(not self.busy and self.approval is not None)
        self.step_button.Enable(active and not self.busy)
        self.run_button.Enable(active)
        self.reset_button.Enable(active and not self.busy and self.approval is not None)
        self.stop_button.Enable(active or self.busy)
        self.uart_send.Enable(active and not self.busy)
        self.circuit_button.Enable(not self.busy and self.block is not None and self.approval is not None and self.trust.GetValue())
    def _live(self, generation):
        return not self.closed and generation == self.generation and not self.IsBeingDeleted()
    def close(self, event=None):
        if self.closed:
            return
        self.closed = True
        self.running = False
        self.timer.Stop()
        self.generation += 1
        session, self.session = self.session, None
        if self.pending:self.executor.submit(self._discard_result,self.pending)
        if session:
            self.executor.submit(session.close)
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.Destroy()
    def _destroyed(self, event):
        if event.GetEventObject() is self and not self.closed:self.close()
        event.Skip()
def show(owner, block=None):
    """Show or raise the owner's one reusable firmware manager."""
    if getattr(owner, "job_running", False):
        raise ValueError("Stop the active circuit job before opening firmware emulation")
    window = _WINDOWS.get(owner)
    if window is None or window.closed or window.IsBeingDeleted():
        window=FirmwareWindow(owner,block)
        _WINDOWS[owner] = window
    else:
        if block is not None:
            window.select_block(block)
        window.Show()
        window.Raise()
    return window
