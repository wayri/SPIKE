# SPDX-License-Identifier: Apache-2.0
"""Presentation glue for saved pin properties and explicit coupling choice."""
from copy import deepcopy
import wx

MODES=('legacy','electrical','timestamped','synchronous','peripheral')
LABELS=('Legacy ideal DI/DO','Native electrical — sampled','Timestamped software GPIO — held inputs',
        'Instruction feedback — experimental','Owned PWM / SPI / I2C — fixed-clock test profile')


def build(window,panel,outer):
    row=wx.WrapSizer(wx.HORIZONTAL)
    row.Add(wx.StaticText(panel,label='Circuit coupling'),0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
    window.coupling_mode=wx.Choice(panel,choices=LABELS)
    window.coupling_mode.SetSelection(MODES.index((window.block or {}).get('firmware_coupling_mode','legacy')))
    window.coupling_mode.SetToolTip('Owned peripherals: STM32F407 PA0 TIM2, PA5/6/7 SPI1, PB6/7 I2C1; explicit clocks10/80/8MHz, functional CPU1us. Timed electrical feedback inside each instruction. No whole-MCU or hardware qualification.')
    window.pad_properties_button=wx.Button(panel,label='Electrical pin properties…')
    window.pad_properties_button.SetToolTip('Signal/supply nets, pull resistances, drive strength, package R/L and rail capacitance')
    row.Add(window.coupling_mode,0,wx.ALL,4);row.Add(window.pad_properties_button,0,wx.ALL,4)
    window.pin_notice=wx.StaticText(panel,label='Generic user-supplied profiles; no vendor pad qualification.')
    row.Add(window.pin_notice,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
    outer.Add(row,0,wx.EXPAND|wx.LEFT|wx.RIGHT,4)
    window.pad_properties_button.Bind(wx.EVT_BUTTON,lambda event:edit(window))
    window.coupling_mode.Bind(wx.EVT_CHOICE,lambda event:save_mode(window))


def _save(window,**changes):
    if window.busy or getattr(window.owner,'job_running',False):raise ValueError('Stop the active job before editing electrical pins')
    if not window.block or not hasattr(window.owner,'doc'):raise ValueError('Place and select a controller board first')
    current=next((b for b in window.owner.doc.data['controller_boards'] if b['id']==window.block['id']),None)
    if current!=window.block:raise ValueError('Board changed; reopen the firmware manager from the current block')
    updated=deepcopy(current);updated.update(changes)
    from .controller_board_blocks import update
    update(window.owner.doc,current['id'],updated)
    window.block=deepcopy(updated)
    refresh=getattr(window.owner,'refresh_document',None)
    if refresh:refresh()


def save_mode(window):
    try:_save(window,firmware_coupling_mode=MODES[window.coupling_mode.GetSelection()])
    except ValueError as exc:
        window.coupling_mode.SetSelection(MODES.index((window.block or {}).get('firmware_coupling_mode','legacy')))
        window.status.SetLabel(str(exc))


def edit(window):
    try:
        if not window.block:raise ValueError('Open this manager from a placed controller board')
        from .firmware_pad_properties import show
        from python.spikes.native_runner import _nodes
        from python.spikes.netlist import parse_netlist
        project=parse_netlist(window.owner.doc.data['source'],native_extensions=True,transient_capture='rolling')
        value=show(window,window.block['board'],window.block.get('electrical_pads'),_nodes(project))
        if value is not None:
            _save(window,electrical_pads=value)
            window.status.SetLabel('Electrical pin properties saved; generic/unqualified model, one undoable change')
    except Exception as exc:window.status.SetLabel('Pin properties: '+str(exc))
