# SPDX-License-Identifier: Apache-2.0
"""Bounded installed-payload checks; no user firmware or hardware is accessed."""
import json
from pathlib import Path
import traceback


def verify(library,check):
    from python.spikes.native_abi import load_native_library
    from python.spikes.native_peripheral import NativePeripheral
    with NativePeripheral(load_native_library(library)) as device:
        device.command(1,10_000_000,0,3,2);device.command(2,1)
        rises=[]
        for _ in range(8):
            event=device.next(2000)
            if event['high_mask']&1:rises.append(event['time_ns'])
            device.resolve(0)
        check(rises==[0,400,800,1200],'owned native peripheral PWM inclusive-counter 400ns period')


def run(library,destination):
    """Explicit trusted runtime check, separate from the timed GUI smoke."""
    from .resources import resource_dir
    from .renode_process import find_runtime
    from .firmware_peripheral import PeripheralFirmwareController
    from .firmware_electrical import PadConnection
    from .firmware_session import number
    from python.spikes.native_abi import load_native_library
    from python.spikes.netlist import parse_netlist
    from python.spikes.native_runner import _populate
    checks={};details={};error=None
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    try:
        verify(library,check)
        fixtures=[
            ('owned_pwm',27,'RLOAD pwm 0 1k\nCLOAD pwm 0 20p',
             [PadConnection('PWM','A',0,'pwm','vdd')]),
            ('owned_spi_loopback',18,'RCLK clk 0 100k\nRDATA data 0 100k\nCDATA data 0 20p',
             [PadConnection('SCK','A',5,'clk','vdd'),PadConnection('MISO','A',6,'data','vdd'),PadConnection('MOSI','A',7,'data','vdd')]),
            ('owned_i2c_address',180,'RPCLK vdd clk 2.2k\nRPDATA vdd data 2.2k\nCCLK clk 0 20p\nCDATA data 0 20p',
             [PadConnection('SCL','B',6,'clk','vdd'),PadConnection('SDA','B',7,'data','vdd')]),
        ]
        for name,count,body,pins in fixtures:
            project=parse_netlist('.title Owned package check\nVDD vdd 0 3.3\n'+body+'\n.tran 1u 200u\n.end\n',native_extensions=True)
            image=resource_dir('docs').parents[1]/('examples/controller_firmware/'+name+'.bin')
            master=PeripheralFirmwareController(find_runtime(),image,'st-stm32f407g-disc1-mb997',pins,step_s=1e-6,trusted=True)
            try:
                master.bind(project)
                with load_native_library(library).circuit() as circuit:
                    _populate(circuit,project);master.configure_circuit(circuit,project)
                    with circuit.transient_session(initialize_from_operating_point=True) as plant:
                        for _ in range(count):master.step_plant(plant,1e-6,lambda:None)
                        register=number(master.session.engine.command("python \"print int(monitor.Machine['sysbus.cpu'].GetRegisterUlong(2))\""))
                        events=list(master.peripheral_events)
                        if name=='owned_pwm':
                            rises=[e['time_ns'] for e in events if e['drive_mask']&1 and e['high_mask']&1]
                            check(len(rises)>=5 and all(b-a==400 for a,b in zip(rises,rises[1:])),name+' actual firmware 400ns recurrence')
                        elif name=='owned_spi_loopback':
                            check(register==0xa5 and sum(bool(e['sample_mask']&8) for e in events)==8,name+' physical loopback eight samples returns A5')
                        else:check(bool(register&(1<<10)) and master.sample_count>9,name+' actual unaddressed bus reports NACK')
                        details[name]={'r2':register,'time_s':plant.time_s,'provenance':master.provenance()}
            finally:master.close()
    except Exception:error=traceback.format_exc()
    Path(destination).write_text(json.dumps({'passed':error is None,'checks':checks,'details':details,'error':error},indent=2)+'\n',encoding='utf-8')
    return int(error is not None)
