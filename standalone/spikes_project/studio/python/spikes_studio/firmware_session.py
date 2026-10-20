# SPDX-License-Identifier: Apache-2.0
"""Explicit native MCU execution; no automatic target substitution or host I/O.

Register maps: Nordic nRF52840 PS GPIO registers; ST RM0090 GPIO register map.
The native engine owns CPU/peripheral execution. Python only controls its
documented monitor and samples GPIO at requested virtual-time boundaries.
"""
import hashlib
import math
from pathlib import Path
import re
from .firmware_image import inspect_image,image_segments,TARGETS
from .renode_process import RenodeProcess


def number(response):
    values=re.findall(r'^\s*(0x[0-9a-fA-F]+|[0-9]+)\s*$',response,re.M)
    if len(values)!=1:raise RuntimeError('Ambiguous native register response')
    return int(values[0],16 if values[0].startswith('0x') else 10)


def gpio_pin(target_id,pin):
    text=' '.join([pin['label'],*pin.get('aliases',[])])
    pattern=r'\bP([01])\.(\d{1,2})\b' if TARGETS[target_id]['flash'][0]==0 else r'\bP([A-I])(\d{1,2})\b'
    matches=set(re.findall(pattern,text))
    if len(matches)!=1:raise ValueError('Pin has no unambiguous admitted MCU GPIO mapping: '+pin['label'])
    port,index=next(iter(matches));index=int(index)
    if index>31 or (port.isalpha() and index>15):raise ValueError('GPIO index out of range')
    return port,index


class FirmwareSession:
    def __init__(self,runtime,image,target_id,*,trusted=False,expected_sha256=None):
        # Inspection and copying never execute an imported artifact.
        self.image=inspect_image(image,target_id);self.target_id=target_id
        if not trusted:raise ValueError('Explicit firmware/runtime trust approval is required')
        if expected_sha256 is not None and self.image['sha256']!=expected_sha256:
            raise ValueError('Firmware changed since approval; inspect and approve its new hash')
        self.engine=RenodeProcess(runtime,trusted=True);self.closed=False;self.time_ns=0
        try:
            self.snapshot=self.engine.work/('firmware.'+self.image['kind'])
            with Path(image).open('rb') as source:payload=source.read(16*1024*1024+1)
            if len(payload)>16*1024*1024:raise ValueError('Firmware changed beyond the image size limit')
            self.snapshot.write_bytes(payload)
            copied=inspect_image(self.snapshot,target_id,self.image['kind'])
            if copied['sha256']!=self.image['sha256']:raise ValueError('Firmware changed while copying')
            self.platform=TARGETS[target_id]['renode_platform']
            self.platform_sha256=hashlib.sha256((self.engine.path.parent/self.platform).read_bytes()).hexdigest()
            self.engine.command('mach create "spikes"')
            self.engine.command('machine LoadPlatformDescription @'+self.platform)
            self.engine.command('sysbus.cpu IsSemihostingEnabled false')
            # Explicit physical ELF loading: .data's LMA belongs in flash,
            # while startup firmware copies it to the SRAM VMA. Never delegate
            # ambiguous VMA/LMA interpretation or section parsing to LoadELF.
            for index,segment in enumerate(image_segments(payload,target_id,self.image['kind'])):
                if not segment['file_size']:continue
                path=self.engine.work/f'segment-{index}.bin'
                path.write_bytes(payload[segment['offset']:segment['offset']+segment['file_size']])
                name=str(path).replace('\\','/').replace(' ','\\ ')
                self.engine.command(f"sysbus LoadBinary @{name} 0x{segment['address']:x}")
            self.engine.command(f"sysbus.cpu VectorTableOffset 0x{TARGETS[target_id]['flash'][0]:x}")
            self.engine.command(f"sysbus.cpu SP 0x{self.image['initial_sp']:x}")
            self.engine.command(f"sysbus.cpu PC 0x{self.image['reset_pc']:x}")
            self.uart_path=self.engine.work/'uart.bin'
            self.uart_device='usart2' if self.is_stm else 'uart0'
            name=str(self.uart_path).replace('\\','/').replace(' ','\\ ')
            self.engine.command(f'sysbus.{self.uart_device} CreateFileBackend @{name} true')
            self.uart_sequence=0
        except BaseException:self.close();raise

    @property
    def is_stm(self):return TARGETS[self.target_id]['flash'][0]!=0

    @property
    def time_s(self):return self.time_ns/1e9

    def run_for(self,seconds):
        if type(seconds) not in (float,int) or not math.isfinite(seconds) or not 1e-9<=seconds<=1:
            raise ValueError('Firmware step must be 1 ns..1 second')
        ns=round(seconds*1e9)
        if abs(ns/1e9-seconds)>1e-15:raise ValueError('Firmware steps must be integer nanoseconds')
        self.engine.command(f'emulation RunFor "{ns/1e9:.9f}"')
        locked=self.engine.command('sysbus.cpu IsLockedUp')
        if len(re.findall(r'^\s*(True|False)\s*$',locked,re.M))!=1:raise RuntimeError('Ambiguous MCU lockup status')
        if re.search(r'^\s*True\s*$',locked,re.M):
            raise RuntimeError('MCU locked up')
        self.time_ns+=ns

    def set_gpio(self,port,pin,level):
        device=self._gpio_device(port,pin)
        if type(level) is not bool:raise ValueError('GPIO input must be a Boolean')
        self.engine.command(f'sysbus.{device} OnGPIO {pin} {str(level).lower()}')

    def _gpio_device(self,port,pin):
        valid='ABCDEFGHI' if self.is_stm else '01'
        if str(port) not in valid or len(str(port))!=1 or type(pin) is not int or not 0<=pin<(16 if self.is_stm else 32):
            raise ValueError('GPIO port / pin out of range')
        if not self.is_stm and str(port)=='1' and pin>15:
            raise ValueError('nRF52840 implements P1.00..P1.15 only')
        return 'gpioPort'+port if self.is_stm else 'gpio'+port

    def read32(self,address):
        if type(address) is not int or not 0<=address<=0xffffffff:raise ValueError('Invalid register address')
        return number(self.engine.command(f'sysbus ReadDoubleWord 0x{address:x}'))

    def gpio_state(self,port):
        self._gpio_device(port,0)
        if self.is_stm:
            base=0x40020000+0x400*(ord(port)-ord('A'))
            return {'input':self.read32(base+0x10),'output':self.read32(base+0x14),'mode':self.read32(base),'output_type':self.read32(base+4)}
        base=0x50000500+0x300*int(port)
        return {'input':self.read32(base+0x10),'output':self.read32(base+4),'direction':self.read32(base+0x14)}

    def output_level(self,port,pin):
        state=self.gpio_state(port)
        configured=((state['mode']>>(pin*2))&3)==1 if self.is_stm else bool(state['direction']&(1<<pin))
        if not configured:raise ValueError(f'Firmware GPIO P{port}.{pin} is not configured as a push-pull digital output; floating/alternate outputs cannot drive a circuit source')
        if self.is_stm and state['output_type']&(1<<pin):raise ValueError('Open-drain outputs need an electrical pull-up model; direct source coupling is unsupported')
        if not self.is_stm and (self.read32(0x50000700+0x300*int(port)+4*pin)>>8)&7>=4:
            raise ValueError('Disconnected / open-drain drive modes cannot directly drive a circuit source')
        return bool(state['output']&(1<<pin))

    def pad_configuration(self,port,pin):
        """Decode electrical mode; never derive R/C values from drive registers."""
        self._gpio_device(port,pin)
        from .firmware_pad_state import decode_stm32,decode_nrf
        if self.is_stm:
            base=0x40020000+0x400*(ord(port)-ord('A'))
            return decode_stm32(self.read32(base),self.read32(base+4),
                self.read32(base+0xc),self.read32(base+8),self.read32(base+0x14),pin)
        return decode_nrf(self.read32(0x50000700+0x300*int(port)+4*pin),
                          self.read32(0x50000504+0x300*int(port)),pin)

    def uart_read(self):
        if not self.uart_path.exists():return b''
        # Renode opens its UART backend exclusively on Windows. Rotate only
        # while paused, so reading never races an open writer or drops bytes.
        name=str(self.uart_path).replace('\\','/').replace(' ','\\ ')
        self.engine.command(f'sysbus.{self.uart_device} CloseFileBackend @{name}')
        if self.uart_path.stat().st_size>65536:
            self.close();raise RuntimeError('UART capture exceeds 64 KiB per acquisition; choose a shorter firmware step')
        data=self.uart_path.read_bytes();self.uart_path.unlink()
        self.uart_sequence+=1;self.uart_path=self.engine.work/f'uart-{self.uart_sequence}.bin'
        name=str(self.uart_path).replace('\\','/').replace(' ','\\ ')
        self.engine.command(f'sysbus.{self.uart_device} CreateFileBackend @{name} true')
        return data

    def uart_send(self,data):
        if not isinstance(data,bytes) or len(data)>256:raise ValueError('UART injection is at most 256 bytes')
        for byte in data:self.engine.command(f'sysbus.{self.uart_device} WriteChar {byte}')

    def provenance(self):
        return {'backend':'Renode 1.17.0 native instruction/peripheral engine','target_id':self.target_id,
                'firmware_sha256':self.image['sha256'],'runtime_exe_sha256':self.engine.digest,
                'platform_sha256':self.platform_sha256,'virtual_time_s':self.time_s,
                'semantics':'functional emulation; GPIO sampled at explicit virtual-time boundaries',
                'electrical_pin_physics':False,'cycle_accurate':False,'hard_real_time_qualified':False}

    def close(self):
        if getattr(self,'closed',False):return
        self.closed=True
        if getattr(self,'engine',None):self.engine.close()

    def __enter__(self):return self

    def __exit__(self,*args):self.close()
