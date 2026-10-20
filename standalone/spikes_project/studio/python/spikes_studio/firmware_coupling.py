# SPDX-License-Identifier: Apache-2.0
"""User-approved, fresh native firmware sessions for Continuous circuit runs."""
from copy import deepcopy
from .firmware_controller import FirmwareController


def run(owner,window):
    if owner.job_running or window.busy:raise ValueError('Stop the active job before starting firmware circuit coupling')
    context=window.attachment_context();block=context['block'];info=context['firmware']
    if not block or not info or not context['approved']:raise ValueError('Place a board, inspect firmware and explicitly approve its hash first')
    if block['board']['id']!=context['target_id']:raise ValueError('Firmware target must match the placed board exactly')
    current=next((b for b in owner.doc.data['controller_boards'] if b['id']==block['id']),None)
    if current!=block:raise ValueError('Board bindings changed; reopen the firmware manager from the current block')
    from .firmware_window import _engineering_seconds
    step=_engineering_seconds(window.duration.GetValue());saved=deepcopy(block)
    mode=saved.get('firmware_coupling_mode','legacy')
    document=owner.doc.data['id'];revision=owner.doc.data['revision'];window.running=False
    def prepare():
        if mode!='legacy':
            from .firmware_pad_settings import connections,settings_by_prefix
            from .firmware_electrical import ElectricalFirmwareController
            from .firmware_timestamped import TimestampedFirmwareController
            from .firmware_synchronous import SynchronousFirmwareController
            from .firmware_peripheral import PeripheralFirmwareController
            cls={'timestamped':TimestampedFirmwareController,'electrical':ElectricalFirmwareController,
                 'synchronous':SynchronousFirmwareController,'peripheral':PeripheralFirmwareController}[mode]
            pads=saved.get('electrical_pads')
            if pads is None:raise ValueError('Configure Electrical pin properties before choosing native electrical coupling')
            return cls(context['runtime_path'],info['path'],saved['board']['id'],connections(pads,saved['board']),
                pin_settings=settings_by_prefix(pads,saved['board']),step_s=step,trusted=True,expected_sha256=info['sha256'])
        return FirmwareController(saved,context['runtime_path'],info['path'],step_s=step,
                                  trusted=True,expected_sha256=info['sha256'])
    def complete(controller):
        try:
            if owner.job_running or owner.doc.data['id']!=document or owner.doc.data['revision']!=revision:
                raise ValueError('Circuit changed during firmware startup; review and run again')
            if not owner.start_interactive(controller_override=controller):
                window.executor.submit(controller.close);return
            window.status.SetLabel('Firmware coupled to Continuous circuit run; use main Pause / Stop controls')
        except BaseException:
            window.executor.submit(controller.close);raise
    window.status.SetLabel('Preparing fresh firmware session: '+mode+' coupling…')
    window._submit(prepare,complete)
