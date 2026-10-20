# SPDX-License-Identifier: Apache-2.0
"""Owned MMIO/native electrical coupling; trusted native tests are opt-in."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
from python.spikes.native_abi import load_native_library
from python.spikes.native_peripheral import NativePeripheral
DLL=os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',str(ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll'))


class NativePeripheralAbiTests(unittest.TestCase):
    def test_pwm_period_and_event_barrier(self):
        with NativePeripheral(load_native_library(DLL)) as p:
            p.command(1,10_000_000,0,3,2);p.command(2,1)
            rises=[]
            for _ in range(8):
                event=p.next(2000)
                with self.assertRaises(Exception):p.next(2000)
                if event['high_mask']&1:rises.append(event['time_ns'])
                p.resolve(0)
            self.assertEqual(rises,[0,400,800,1200])


@unittest.skipUnless(os.environ.get('SPIKES_TEST_FIRMWARE')=='1','opt-in real MCU / owned native peripheral / electrical plant')
class FirmwarePeripheralNativeTests(unittest.TestCase):
    def run_fixture(self,kind,steps,image_bytes=None):
        from scripts.make_spikes_peripheral_examples import pwm,spi,i2c
        from spikes_studio.firmware_peripheral import PeripheralFirmwareController
        from spikes_studio.firmware_electrical import PadConnection
        from spikes_studio.renode_process import find_runtime
        from python.spikes.netlist import parse_netlist
        from python.spikes.native_runner import _populate
        if kind=='pwm':
            source='.title Owned PWM\nVDD vdd 0 3.3\nRLOAD pwm 0 1k\nCLOAD pwm 0 20p\n.tran 1u 100u\n.end\n'
            pins=[PadConnection('PWM','A',0,'pwm','vdd')]
        elif kind=='spi':
            source='.title Owned SPI\nVDD vdd 0 3.3\nRCLK clk 0 100k\nRDATA data 0 100k\nCDATA data 0 20p\n.tran 1u 100u\n.end\n'
            pins=[PadConnection('SCK','A',5,'clk','vdd'),PadConnection('MISO','A',6,'data','vdd'),PadConnection('MOSI','A',7,'data','vdd')]
        else:
            source='.title Owned I2C\nVDD vdd 0 3.3\nRPCLK vdd clk 2.2k\nRPDATA vdd data 2.2k\nCCLK clk 0 20p\nCDATA data 0 20p\n.tran 1u 200u\n.end\n'
            pins=[PadConnection('SCL','B',6,'clk','vdd'),PadConnection('SDA','B',7,'data','vdd')]
        project=parse_netlist(source,native_extensions=True)
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'owned.bin';image.write_bytes(image_bytes if image_bytes is not None else {'pwm':pwm,'spi':spi,'i2c':i2c}[kind]())
            master=PeripheralFirmwareController(find_runtime(),image,'st-stm32f407g-disc1-mb997',pins,step_s=1e-6,trusted=True)
            try:
                master.bind(project)
                with load_native_library(DLL).circuit() as c:
                    _populate(c,project);master.configure_circuit(c,project)
                    with c.transient_session(initialize_from_operating_point=True) as plant:
                        rows=[]
                        for _ in range(steps):master.step_plant(plant,1e-6,lambda:rows.append(plant.time_s))
                        result={'events':list(master.peripheral_events),'rows':rows,'provenance':master.provenance(),
                            'r2':master.session.engine.command("python \"print int(monitor.Machine['sysbus.cpu'].GetRegisterUlong(2))\"")}
                        return result
            finally:master.close()

    def test_real_firmware_pwm_is_400ns_not_old_300ns(self):
        result=self.run_fixture('pwm',27)
        rises=[e['time_ns'] for e in result['events'] if e['drive_mask']&1 and e['high_mask']&1]
        self.assertGreaterEqual(len(rises),5)
        self.assertTrue(all(b-a==400 for a,b in zip(rises,rises[1:])))
        self.assertTrue(any(ns%1000 for ns in rises))

    def test_real_spi_register_read_uses_electrical_loopback_inside_instruction(self):
        from spikes_studio.firmware_session import number
        result=self.run_fixture('spi',18)
        self.assertEqual(number(result['r2']),0xa5)
        self.assertEqual(sum(bool(e['sample_mask']&8) for e in result['events']),8)
        self.assertTrue(any(e['time_ns']%1000 for e in result['events']))

    def test_real_i2c_register_reports_physical_nack_without_target(self):
        from spikes_studio.firmware_session import number
        result=self.run_fixture('i2c',180)
        self.assertTrue(number(result['r2'])&(1<<10))
        self.assertGreater(result['provenance']['peripheral_samples'],9)

    def test_rcc_resets_and_clock_gates_fail_closed(self):
        from scripts.make_spikes_peripheral_examples import Firmware
        for offset,mask in ((0x20,1),(0x20,1<<21),(0x24,1<<12),
                            (0x30,1),(0x40,0),(0x44,1<<12)):
            with self.subTest(offset=offset,mask=mask):
                firmware=Firmware();firmware.write(0x40023800+offset,mask)
                with self.assertRaisesRegex(RuntimeError,'rejected state'):
                    self.run_fixture('pwm',3,firmware.finish())


if __name__=='__main__':unittest.main()
