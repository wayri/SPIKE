"""Self-closing packaged GUI + spawned native-solver acceptance check."""
import json
from pathlib import Path
import time
import traceback


def worker_timed_out(worker_started,now):
    """The spawned-worker budget excludes earlier, separately bounded fixtures."""
    return worker_started is not None and now-worker_started>60


def run(library,destination):
    import wx
    from .desktop import Studio
    from .resources import resource_dir
    from .run_control import BatchRun
    from .document import RC_DECK
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    app=wx.App(False);app.SetAssertMode(wx.APP_ASSERT_EXCEPTION)
    frame=Studio(str(library));frame.Show();checks={};started=time.monotonic();job=None;worker_started=None
    def finish(error=None):
        if job and job.state=='running':job.stop()
        now=time.monotonic()
        destination.write_text(json.dumps({'passed':error is None,'checks':checks,'error':error,
            'acceptance_elapsed_s':now-started,'worker_elapsed_s':None if worker_started is None else now-worker_started,
            'worker_budget_s':60,'platform':__import__('platform').platform(),'library':str(library)},indent=2)+'\n',encoding='utf-8')
        frame.timer.Stop();frame.Destroy()
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def poll():
        try:
            if worker_timed_out(worker_started,time.monotonic()):raise TimeoutError('Packaged native worker exceeded 60 seconds')
            job.poll()
            if job.state=='running':wx.CallLater(100,poll);return
            if job.state!='completed':raise AssertionError('Spawned native transient failed: '+str(job.error))
            check(True,'spawned native transient completed')
            result=job.result
            check(result['status']=='completed','packaged solver reports completion')
            check(bool(result['data']),'packaged native waveform exists')
            measurement=result.get('measurements',{}).get('startup_probe',{})
            check(measurement.get('status')=='completed','spawned worker loads lightweight measurement reducer')
            check(__import__('math').isfinite(measurement['value']),'spawned measurement returns a finite recorded voltage')
            finish()
        except Exception:finish(traceback.format_exc())
    def begin():
        nonlocal job,worker_started
        try:
            check(library.is_file(),'native engine bundled')
            from .gpio_package_checks import verify as verify_gpio
            verify_gpio(library,check)
            from .peripheral_package_checks import verify as verify_peripheral
            verify_peripheral(library,check)
            from .gpio_package_checks import verify_ui as verify_gpio_ui
            verify_gpio_ui(frame,check)
            if __import__('os').name=='nt':
                from python.spikes.netlist import parse_netlist
                from python.spikes.native_runner import run_native_project
                for family in ('BSIMBULK','BSIMCMG'):
                    deck=f'.title BSIM package\nVd d 0 1\nVg g 0 PULSE(0 1 1n 1n 1n 10n 20n)\nM1 d g 0 0 mm\n.model mm {family}()\n.tran 100p 4n\n.end'
                    result=run_native_project(parse_netlist(deck,native_extensions=True),str(library),integration_method='backward_euler').to_dict()
                    check(result['status']=='completed',family+' packaged charge transient')
                    check(max(abs(v) for v in result['data']['element_current_a']['VG'])>1e-10,family+' gate displacement current')
            check((resource_dir('docs')/'COMPONENT_LIBRARY.md').is_file(),'current illustrated library guide bundled')
            check(len(frame.symbols)>1,'real schematic symbol library loaded')
            panel=frame.catalog_panel;panel.search.ChangeValue('family:resistor');panel.filter()
            # The passive library has expanded beyond the original 50 presets.
            # Compare complete identities against an independent field predicate,
            # not an obsolete fixed count or merely a nonempty search result.
            expected={row['id'] for row in panel.catalog['records']
                      if 'resistor' in row['family'].casefold()}
            actual={row['id'] for row in panel.visible}
            check(bool(expected) and actual==expected and len(actual)==len(panel.visible),
                  'catalog search works')
            from .library_package_checks import verify as verify_library_packages
            verify_library_packages(frame,library,check)
            from .part_form_checks import verify as verify_part_forms
            verify_part_forms(frame,check)
            from .controller_boards import records
            from .firmware_image import TARGETS
            from .firmware_window import FirmwareWindow
            check(len(records())==17,'expanded sourced controller board library bundled')
            manager=FirmwareWindow(frame)
            check(set(manager.target_ids)==set(TARGETS),'native firmware manager exposes only admitted board targets')
            check(manager.session is None and not manager.trust.GetValue(),'opening firmware manager never executes or grants trust')
            manager.close()
            hub=frame.manufacturer_hub
            check(len(hub.products.catalog['records'])==208,'208 sourced manufacturer identities bundled separately from generic presets')
            hub.products.search.SetValue('AD620');hub.products.refresh()
            check(any(row['part_number']=='AD620' for row in hub.products.listing.rows),'manufacturer product search uses real product identities')
            from .manufacturer_executable_package_checks import verify as verify_manufacturer_executables
            verify_manufacturer_executables(library,check)
            from .ltspice_local_library import index_library,read_model_declaration
            import tempfile
            with tempfile.TemporaryDirectory() as folder:
                sample=Path(folder)/'own-fixture.mod'
                sample.write_bytes('.model PACKAGECHECK D(Is=1p)\n* retained comment\n+ N=1.5\n'.encode('utf-16-le'))
                inventory=index_library(folder);card=read_model_declaration(inventory,inventory['models'][0]['id'])
                check('N=1.5' in card,'local model index preserves UTF16 comment-separated continuations')
                check('original_source' not in inventory['models'][0],'metadata index does not embed vendor model bodies')
            import os
            if os.environ.get('SPIKES_TEST_FIRMWARE')=='1':
                from .renode_process import find_runtime
                from .firmware_session import FirmwareSession
                image=resource_dir('docs').parents[1]/'examples/controller_firmware/nrf52840_gpio_echo.bin'
                with FirmwareSession(find_runtime(),image,'nordic-nrf52840-dk-pca10056-r3-0-2',trusted=True) as firmware:
                    firmware.run_for(.0001);firmware.set_gpio('0',2,True);firmware.run_for(.0001)
                    check(firmware.output_level('0',3),'packaged native firmware executes GPIO instructions')
                    firmware.uart_send(b'K');firmware.run_for(.01)
                    check(firmware.uart_read()==b'K','packaged native UARTE EasyDMA echo')
                from .firmware_edge_transport import FirmwareEdgeTransport
                with FirmwareSession(find_runtime(),image,'nordic-nrf52840-dk-pca10056-r3-0-2',trusted=True) as firmware:
                    edges=FirmwareEdgeTransport(firmware,[('0',3)]).run_for_ns(1000)
                    check(bool(edges) and all(e['time_ns']>0 for e in edges),
                          'packaged timestamp collector records actual virtual GPIO changes')
                from .firmware_sync_transport import FirmwareSyncTransport
                image=image.with_name('nrf52840_gpio_only_echo.bin')
                with FirmwareSession(find_runtime(),image,'nordic-nrf52840-dk-pca10056-r3-0-2',trusted=True) as firmware:
                    sync=FirmwareSyncTransport(firmware,[('0',2),('0',3)])
                    for level in (True,False):
                        for _ in range(20):
                            sync.set_inputs([('0',2,level)])
                            sync.step()
                        check(firmware.output_level('0',3)==level,
                              'packaged instruction feedback observes input '+str(level))
                    check(sync.time_ns==400,'packaged CPU advances exactly one instruction per feedback boundary')
            from .workflow_package_checks import verify as verify_workflow
            verify_workflow(frame,check)
            from .wiring_package_checks import verify as verify_wiring
            verify_wiring(frame,check,destination.parent/(destination.stem+'-ui'))
            frame.pin_browser(True);check(panel.GetParent() is frame.browser_side,'browser pins')
            frame.canvas.selected={frame.doc.data['components'][1]['id']};frame.pin_properties(True)
            check(frame.properties_editor is not None,'editable properties pin')
            frame.toggle_part_shortcuts(False);check(not frame.keymap.part_shortcuts,'part shortcuts disable')
            frame.set_theme('Light',save=False);frame.set_theme('Dark',save=False)
            from .model_preview import ModelPreview
            preview=ModelPreview(frame)
            preview.update_model(frame.doc.data['components'][2],{'esr_ohm':2,'esl_h':1e-6,'leakage_ohm':1e6},frame.doc.data['source'])
            preview.figure.savefig(destination.with_suffix('.preview.png'))
            check(len(preview.figure.axes)==2,'graphical model and analytical curve render')
            preview.Destroy()
            measured=RC_DECK.replace('.end','.meas tran startup_probe FIND V(out) AT=1m\n.end')
            worker_started=time.monotonic()
            job=BatchRun(measured,str(library));wx.CallLater(100,poll)
        except Exception:finish(traceback.format_exc())
    wx.CallLater(400,begin);app.MainLoop()
    return 0 if destination.is_file() and json.loads(destination.read_text())['passed'] else 1
