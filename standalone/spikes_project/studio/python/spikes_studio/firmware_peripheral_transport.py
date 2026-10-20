# SPDX-License-Identifier: Apache-2.0
"""Explicit replacement of three inactive native blocks by owned MMIO service.

No upstream timer adjustment, byte-return SPI shortcut or fabricated I2C ACK.
Pin routing and clocks are an admitted experimental subset, not full STM32.
"""
from copy import deepcopy
from pathlib import Path
import re
from .firmware_sync_transport import FirmwareSyncTransport
from .firmware_pipe import FirmwarePipe
from .firmware_pad_state import decode_stm32
from .firmware_edge_transport import admit_events

# Signal bit -> (GPIO port,pin,alternate-function index).
ROUTES={1:('A',0,1),2:('A',5,5),4:('A',7,5),8:('A',6,5),
        16:('B',6,4),32:('B',7,4)}


class FirmwarePeripheralTransport(FirmwareSyncTransport):
    step_ns=1000  # Explicit functional CPU cadence; peripheral clocks independent.

    def __init__(self,session,pins,callback,input_callback):
        if not session.is_stm:raise ValueError('Owned peripheral subset requires the admitted STM32F407 target')
        self.routes={};self.callback=callback;self.pipe=None
        self.input_callback=input_callback
        super().__init__(session,pins)
        try:
            self.pipe=FirmwarePipe(callback)
            hook=str(Path(__file__).with_name('renode_peripheral_hook.py').resolve())
            session.engine.command('include @'+hook.replace('\\','/').replace(' ','\\ '))
            session.engine.command('sysbus.cpu PerformanceInMips 1')
            # This fixed-clock profile has no RCC gate/reset lifecycle. Even
            # enabling writes must not imply register-driven clock semantics.
            session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.rcc "import sys; value = sys._spikes_sync.reject()"')
            session.engine.command('python "import sys; sys._spikes_sync = sys._spikes_peripheral_collector_type(monitor.Machine, %r, %d, %r, %r, %d)"' %
                (self.ports,self.capacity,self.pipe.name,self.pipe.token,self.step_ns))
            blocks=[]
            for device,(name,address) in enumerate((('timer2',0x40000000),('spi1',0x40013000),('i2c1',0x40005400))):
                session.engine.command('sysbus Unregister sysbus.'+name)
                blocks.extend([
                    'spikesOwned%d: Python.PythonPeripheral @ sysbus 0x%x'%(device,address),
                    '    size: 0x400','    initable: false',
                    '    script: "import sys; request.Value = sys._spikes_sync.exchange(%d, request.IsWrite, request.Offset, request.Value, request.Length)"'%device])
            for port in self.ports:
                device=3+ord(port)-ord('A');address=0x40020000+0x400*(device-3)
                session.engine.command('sysbus Unregister sysbus.gpioPort'+port)
                blocks.extend(['spikesOwnedGPIO%s: Python.PythonPeripheral @ sysbus 0x%x'%(port,address),
                    '    size: 0x400','    initable: false',
                    '    script: "import sys; request.Value = sys._spikes_sync.exchange(%d, request.IsWrite, request.Offset, request.Value, request.Length)"'%device])
            session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.dma2 "import sys; value = sys._spikes_sync.reject()"')
            platform=session.engine.work/'owned-peripherals.repl'
            platform.write_text('\n'.join(blocks)+'\n',encoding='utf-8')
            session.engine.command('machine LoadPlatformDescription @'+str(platform).replace('\\','/').replace(' ','\\ '))
        except BaseException:
            session.close();self.close();raise

    def _config(self,port,pin,words):
        mode,otype,pull,speed,odr,afr0,afr1=words
        alternate=(mode>>(2*pin))&3
        identity=port,pin
        signal=next((bit for bit,route in ROUTES.items() if route[:2]==identity),None)
        route=None
        if alternate==2:
            af=((afr0 if pin<8 else afr1)>>(4*(pin%8)))&15
            if signal is None or ROUTES[signal][2]!=af:
                raise RuntimeError('Unsupported alternate-function route: P%s%d AF%d'%(port,pin,af))
            if signal in (16,32) and not (otype&(1<<pin)):
                raise RuntimeError('I2C alternate-function pins must be open drain')
            route=signal
            # Translate only the electrical direction, not the peripheral state
            # machine. The owned native service controls actual timed outputs.
            # Inactive peripheral outputs are released. Timed native events,
            # not an unconnected GPIO ODR latch, subsequently own their drive.
            direction=0
            mode=(mode&~(3<<(2*pin)))|(direction<<(2*pin))
            odr &= ~(1<<pin)
        config=decode_stm32(mode,otype,pull,speed,odr,pin)
        if route:config['owned_peripheral_signal']=route
        return config

    def _decode(self,text):
        if 'SPIKES_SYNC_FAILED' in text:raise RuntimeError('Owned peripheral instruction %d rejected state or callback failure: '%self.steps+text[-2000:])
        rows=re.findall(r'^\s*SPIKES_SYNC_V1 (\d+) ([A-I]) (\d+) ([0-9 ]+)\s*$',text,re.M)
        ends=re.findall(r'^\s*SPIKES_SYNC_END (\d+) (\d+) (\d+)\s*$',text,re.M)
        if len(ends)!=1 or int(ends[0][0])!=len(rows) or len(rows)>self.capacity or len(re.findall(r'^\s*SPIKES_SYNC_V1\b',text,re.M))!=len(rows):
            raise RuntimeError('Incomplete owned peripheral instruction batch')
        _,start,end=map(int,ends[0])
        if start!=self.time_ns or end!=start+self.step_ns:raise RuntimeError('Owned peripheral clock mismatch')
        staged=deepcopy(self.states);events=[];routes=dict(self.routes)
        for stamp,port,pin_text,word_text in rows:
            pin=int(pin_text);words=[int(n) for n in word_text.split()]
            if int(stamp)!=start or (port,pin) not in staged or len(words)!=7:
                raise RuntimeError('Invalid owned peripheral GPIO observation')
            config=self._config(port,pin,words)
            if config!=staged[port,pin]:
                events.append({'time_ns':start,'port':port,'pin':pin,'config':config})
                staged[port,pin]=config
            for signal,route in ROUTES.items():
                if route[:2]==(port,pin):
                    if config.get('owned_peripheral_signal')==signal:routes[signal]=(port,pin)
                    else:routes.pop(signal,None)
        result=admit_events(events,start,end,capacity=self.capacity)
        self.states=staged;self.routes=routes
        return {'start_ns':start,'end_ns':end,'events':result}

    def close(self):
        if self.pipe is not None:self.pipe.close();self.pipe=None

    def set_inputs(self,inputs):
        seen=set()
        for port,pin,level in inputs:
            if (port,pin) not in self.states or (port,pin) in seen or type(level) is not bool:
                raise ValueError('Invalid owned GPIO input batch')
            seen.add((port,pin))
        self.input_callback(inputs)

    def provenance(self):
        return {**super().provenance(),'timing_mode':'owned_native_peripheral_mmio',
            'cpu_instruction_period_ns':self.step_ns,
            'peripheral_backend':'SPIKES C++ explicit timer/SPI/I2C replacement',
            'pin_routes':{'PA0':'TIM2_CH1 AF1','PA5/PA6/PA7':'SPI1 AF5','PB6/PB7':'I2C1 AF4'},
            'clocks_hz':{'timer':10_000_000,'spi_input':80_000_000,'i2c_input':8_000_000},
            'rcc_policy':'all RCC writes rejected; clocks fixed, no gate/reset semantics',
            'excluded':['other pin routes','interrupt/DMA peripheral operation','RCC/PLL inference','cycle accuracy','physical SI/PI qualification']}
