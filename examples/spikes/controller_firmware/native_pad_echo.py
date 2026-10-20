# SPDX-License-Identifier: Apache-2.0
"""Run the original nRF52840 echo image with owned finite electrical pads.

Explicit approval is required. This is sampled functional co-simulation, not
event-accurate SPI/I2C, vendor calibration, or physical SI/PI qualification.
"""
import argparse
import csv
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
studio=ROOT/'studio/python'
if not studio.is_dir():studio=ROOT/'standalone/spikes_project/studio/python'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(studio))


def main():
    from spikes_studio.firmware_electrical import ElectricalFirmwareController,PadConnection
    from spikes_studio.renode_process import find_runtime
    from python.spikes.native_abi import load_native_library
    from python.spikes.native_io_pad import PadProfile,observe_pad
    from python.spikes.native_runner import _populate
    from python.spikes.netlist import parse_netlist
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,default=ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll')
    parser.add_argument('--runtime',type=Path,default=find_runtime())
    parser.add_argument('--firmware',type=Path,default=Path(__file__).with_name('nrf52840_gpio_echo.bin'))
    parser.add_argument('--approve-firmware',action='store_true',help='Explicitly trust the selected firmware and reviewed runtime')
    parser.add_argument('--csv',type=Path,help='Optional sample export')
    args=parser.parse_args()
    if not args.approve_firmware:parser.error('Inspect the selected image first; execution requires --approve-firmware')
    profile=PadProfile(package_resistance_ohm=1,package_inductance_h=5e-9,
                       capacitance_to_vss_f=5e-12,capacitance_to_vdd_f=2e-12)
    source='Electrical GPIO example\nVSUPPLY supply 0 3.3\nRPDN supply vdd 1\nVIN input 0 0\nRLOAD output 0 1k\nCLOAD output 0 1n\n.tran 10u 2m\n.end\n'
    project=parse_netlist(source)
    bridge=ElectricalFirmwareController(args.runtime,args.firmware,'nordic-nrf52840-dk-pca10056-r3-0-2',[
        PadConnection('P02','0',2,'input','vdd',profile=profile),
        PadConnection('P03','0',3,'output','vdd',profile=profile)],trusted=True)
    rows=[]
    try:
        bridge.bind(project)
        with load_native_library(args.library).circuit() as circuit:
            _populate(circuit,project);bridge.configure_circuit(circuit,project)
            with circuit.transient_session(initialize_from_operating_point=True) as plant:
                for index in range(60):
                    if index==10:plant.set_source_value('VIN',3.3)
                    if index==40:plant.set_source_value('VIN',0)
                    bridge.advance(plant)
                    if not plant.step(1e-5):raise RuntimeError(plant.message)
                    rows.append({'time_s':plant.time_s,**observe_pad(plant,'P03')})
    finally:bridge.close()
    if args.csv:
        with args.csv.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    print('Owned C++ pad network; sampled nRF52840 instruction backend.')
    print(f"Output range: {min(r['pad_voltage_v'] for r in rows):.6g} .. {max(r['pad_voltage_v'] for r in rows):.6g} V")
    print('Finite 500-ohm generic standard drive, actual supply impedance, package R/L and split capacitance.')
    print('Synthetic profile; no manufacturer or high-speed SI/PI qualification.')


if __name__=='__main__':main()
