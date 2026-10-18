# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import tempfile
import struct
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'standalone/spikes_project/studio/python'))
from spikes_studio.renode_process import RenodeProcess,find_runtime
from spikes_studio.firmware_session import FirmwareSession
from spikes_studio.firmware_controller import FirmwareController
from spikes_studio.controller_boards import get_record
from spikes_studio.controller_board_blocks import create
from scripts.make_spikes_firmware_examples import gpio_echo

RUN_NATIVE=os.environ.get('SPIKES_TEST_FIRMWARE')=='1'
NRF='nordic-nrf52840-dk-pca10056-r3-0-2'
STM='st-stm32f407g-disc1-mb997'


@unittest.skipUnless(RUN_NATIVE,'opt-in real native emulator tests')
class FirmwareNativeTests(unittest.TestCase):
    def fixture(self,folder,stm=False):
        path=Path(folder)/'echo.bin';path.write_bytes(gpio_echo(stm));return path

    def test_nrf_binary_gpio_and_uarte_dma_execute(self):
        with tempfile.TemporaryDirectory() as folder:
            with FirmwareSession(find_runtime(),self.fixture(folder),NRF,trusted=True) as session:
                session.run_for(.0001)
                for state in (True,False,True):
                    session.set_gpio('0',2,state);session.run_for(.0001)
                    self.assertEqual(session.output_level('0',3),state)
                session.uart_send(b'K');session.run_for(.01)
                self.assertEqual(session.uart_read(),b'K')
                self.assertEqual(session.uart_read(),b'')
                self.assertGreater(session.time_ns,0)
                self.assertIn('00:00:00.010400000',session.engine.command('machine GetTimeSourceInfo'))
            self.assertIsNotNone(session.engine.process.poll())

    def test_stm32_binary_gpio_executes_after_initialization(self):
        with tempfile.TemporaryDirectory() as folder:
            with FirmwareSession(find_runtime(),self.fixture(folder,True),STM,trusted=True) as session:
                session.run_for(.0001)
                for state in (True,False):
                    session.set_gpio('B',2,state);session.run_for(.0001)
                    self.assertEqual(session.output_level('B',3),state)

    def test_nano33_same_cpu_executes_own_matching_image(self):
        with tempfile.TemporaryDirectory() as folder:
            with FirmwareSession(find_runtime(),self.fixture(folder),'arduino-nano-33-ble-abx00030',trusted=True) as session:
                session.run_for(.0001);session.set_gpio('0',2,True);session.run_for(.0001)
                self.assertTrue(session.output_level('0',3))

    def test_native_elf_physical_load_preserves_sram_initializer_lma(self):
        payload=gpio_echo();lma=(len(payload)+3)&~3
        header=bytearray(0x100)
        header[:16]=b'\x7fELF\x01\x01\x01'+bytes(9)
        struct.pack_into('<HHIIIIIHHHHHH',header,16,2,40,1,0x101,52,0,0,52,32,2,0,0,0)
        struct.pack_into('<IIIIIIII',header,52,1,0x100,0,0,len(payload),len(payload),5,4)
        data_offset=0x100+lma
        struct.pack_into('<IIIIIIII',header,84,1,data_offset,0x20001000,lma,4,8,6,4)
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'split.elf';image.write_bytes(bytes(header)+payload+bytes(lma-len(payload))+b'INIT')
            with FirmwareSession(find_runtime(),image,NRF,trusted=True) as session:
                self.assertEqual(session.read32(lma),0x54494e49)
                self.assertEqual(session.read32(0x20001000),0)
                session.run_for(.0001);session.set_gpio('0',2,True);session.run_for(.0001)
                self.assertTrue(session.output_level('0',3))

    def test_cpp_plant_pause_resume_and_firmware_runtime_cleanup(self):
        from spikes_studio.document import Document
        from spikes_studio.run_control import InteractiveRun
        library=ROOT/'build-spikes-native-analysis-20261013/Release/spikes_c_api.dll'
        if not library.is_file():self.skipTest('native circuit library unavailable')
        document=Document.load(ROOT/'examples/spikes/controller_firmware/stm32f407_gpio_rc.spksch')
        with tempfile.TemporaryDirectory() as folder:
            bridge=FirmwareController(document.data['controller_boards'][0],find_runtime(),self.fixture(folder,True),trusted=True)
            run=InteractiveRun(document.data['source'],library,controller=bridge,capacity=100)
            def wait(predicate):
                deadline=time.monotonic()+20
                while not predicate():
                    if run.state=='failed':self.fail(run.error)
                    if time.monotonic()>deadline:self.fail('native firmware / plant wait timed out')
                    time.sleep(.01)
            try:
                wait(lambda:run.total_samples>=3)
                run.pause();wait(lambda:run.state=='paused')
                count=run.total_samples;time.sleep(.05);self.assertEqual(run.total_samples,count)
                run.set_source('VSENSE',3);run.resume()
                wait(lambda:any(e['origin']=='firmware_gpio' and e['value']==3 for e in run.control_events if 'origin' in e))
                self.assertEqual(run.snapshot()['provenance']['controller']['target_id'],STM)
            finally:run.stop();run.thread.join(timeout=20)
            self.assertFalse(run.thread.is_alive());self.assertIsNotNone(bridge.session.engine.process.poll())

    def test_untrusted_changed_image_and_bad_command_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            image=self.fixture(folder)
            with self.assertRaisesRegex(ValueError,'trust'):FirmwareSession(find_runtime(),image,NRF)
            with self.assertRaisesRegex(ValueError,'changed'):FirmwareSession(find_runtime(),image,NRF,trusted=True,expected_sha256='0'*64)
        runtime=RenodeProcess(find_runtime(),trusted=True)
        with self.assertRaisesRegex(RuntimeError,'rejected'):runtime.command('not_a_real_command')
        self.assertIsNotNone(runtime.process.poll())

    def test_firmware_circuit_bridge_uses_real_pin_maps(self):
        block=create(get_record(STM),0,0)
        for label,mode in (('PB2','DI'),('PB3','DO')):
            pin=next(p for p in block['board']['pins'] if p['label']==label)
            block['bindings'][pin['id']].update(mode=mode,node='sense' if mode=='DI' else '',reference='0' if mode=='DI' else '',source='VDRIVE' if mode=='DO' else '')
        with tempfile.TemporaryDirectory() as folder:
            bridge=FirmwareController(block,find_runtime(),self.fixture(folder,True),trusted=True)
            try:
                name=bridge.inputs[0]['name'];bridge.step({name:0},0,.0001)
                self.assertEqual(bridge.step({name:3.},.0001,.0001),{'VDRIVE':3.})
                self.assertEqual(bridge.step({name:0},.0002,.0001),{'VDRIVE':0.})
            finally:bridge.close()


if __name__=='__main__':unittest.main()
