# SPDX-License-Identifier: Apache-2.0
"""Executed pad acceptance shared by source, frozen and installed Studio."""
def verify(path,check):
    from python.spikes.native_abi import load_native_library
    from python.spikes.native_io_pad import require_io_pad_api,add_pad,PadState,set_pad,receive,observe_pad
    library=load_native_library(path)
    require_io_pad_api(library)
    check(True,'bundled native engine exposes the complete electrical GPIO pad API')
    with library.circuit() as circuit:
        circuit.add_voltage_source('supply','vdd','0',3.3)
        circuit.add_resistor('load','pin','0',50000)
        add_pad(circuit,'U1.P1','pin','vdd','0',initial=PadState(pull='up'))
        with circuit.transient_session(initialize_from_operating_point=True) as session:
            check(session.step(1e-6),'bundled GPIO circuit accepts a native transient point')
            check(abs(session.node_voltage('pin')-1.65)<1e-7,'bundled finite GPIO pull solves the expected divider voltage')
            with session.checkpoint() as checkpoint:
                set_pad(session,'U1.P1',PadState(mode='push_pull',output='high'))
                check(session.step(2e-6) and session.node_voltage('pin')>3.29,'bundled GPIO state update reaches the native circuit')
                session.restore(checkpoint)
            values=observe_pad(session,'U1.P1')
            check(abs(values['pad_voltage_v']-1.65)<1e-7,'bundled GPIO checkpoint restores the accepted electrical state')
            check(receive(session,3.3,3.3,0)=='high','bundled native GPIO receiver classifies the supplied rail voltage')
    from python.spikes.native_io_pad import schedule_pad_edge,pending_pad_edges
    with library.circuit() as c:
        c.add_voltage_source('V','vdd','0',1);c.add_capacitor('C','pin','0',1e-9)
        add_pad(c,'edge','pin','vdd','0',initial=PadState('push_pull','low'))
        with c.transient_session() as s:
            schedule_pad_edge(s,'edge',23,PadState('push_pull','high'))
            schedule_pad_edge(s,'edge',67,PadState('push_pull','low'))
            check(s.step(100e-9) and s.node_voltage('pin')>.1 and pending_pad_edges(s)[0]==0,
                  'bundled native scheduler retains two subinterval GPIO edges')


def verify_ui(frame,check):
    from .controller_boards import get_record
    from .firmware_pad_properties import FirmwarePadPropertiesDialog
    import wx
    dialog=FirmwarePadPropertiesDialog(frame,get_record('nordic-nrf52840-dk-pca10056-r3-0-2'),net_names=('pin','vdd','0'))
    try:
        check(all(name in dialog.fields for name in ('pull_up_resistance_ohm','low_strong_resistance_ohm','package_inductance_h','capacitance_to_vdd_f')),
              'packaged pin editor exposes labeled pull drive and parasitic controls')
        dialog.accept();check(dialog.result is not None,'packaged pin editor validates inert settings without executing code')
    finally:dialog.Destroy()
    from pathlib import Path
    from . import firmware_edge_transport
    check(Path(firmware_edge_transport.__file__).with_name('renode_edge_hook.py').is_file(),
          'owned timestamp collector source is bundled for the explicit runtime')
    from . import firmware_sync_transport
    from .firmware_pin_workflow import MODES
    check('synchronous' in MODES and Path(firmware_sync_transport.__file__).with_name('renode_sync_hook.py').is_file(),
          'instruction-feedback mode and original native hook source are bundled')
