# SPDX-License-Identifier: Apache-2.0
"""Original tiny firmware fixtures for explicit owned-peripheral admission."""
from pathlib import Path
import struct


class Firmware:
    def __init__(self):
        self.data=bytearray(256);self.literals=[]
        struct.pack_into('<II',self.data,0,0x20020000,0x08000101)
    def emit(self,value):self.data.extend(struct.pack('<H',value))
    def load(self,register,value):
        self.literals.append((len(self.data),register,value));self.emit(0)
    def write(self,address,value):self.load(0,address);self.load(1,value);self.emit(0x6001)
    def read(self,address,register=2):self.load(0,address);self.emit(0x6800|register)
    def nops(self,count):
        for _ in range(count):self.emit(0xbf00)
    def finish(self):
        # Leave a bounded straight-line observation interval before the terminal
        # self-branch (which a functional emulator can idle-skip).
        self.nops(32)
        self.emit(0xe7fe)
        while len(self.data)%4:self.data.append(0)
        for position,register,value in self.literals:
            displacement=(len(self.data)-((position+4)&~3))//4
            if not 0<=displacement<=255:raise ValueError('Fixture literal range exceeded')
            struct.pack_into('<H',self.data,position,0x4800|(register<<8)|displacement)
            self.data.extend(struct.pack('<I',value))
        return bytes(self.data)


def pwm():
    f=Firmware();f.write(0x40020020,1);f.write(0x40020000,2)
    for offset,value in ((0x28,0),(0x2c,3),(0x34,2),(0x18,0x60),(0x20,1),(0,1)):
        f.write(0x40000000+offset,value)
    return f.finish()


def spi():
    f=Firmware();f.write(0x40020020,0x55500000)
    f.write(0x40020000,sum(2<<(2*p) for p in (5,6,7)))
    f.write(0x40013000,0x34c);f.write(0x4001300c,0xa5)
    f.read(0x40013008,3);f.read(0x4001300c,2)
    return f.finish()


def i2c():
    f=Firmware();f.write(0x40020404,(1<<6)|(1<<7));f.write(0x40020420,0x44000000)
    f.write(0x40020400,(2<<12)|(2<<14))
    for offset,value in ((4,8),(0x1c,40),(0,1),(0,0x101)):
        f.write(0x40005400+offset,value)
    f.nops(20);f.read(0x40005414,3);f.write(0x40005410,0xa0)
    f.nops(120);f.read(0x40005414,2);f.write(0x40005400,0x201)
    return f.finish()


def main():
    folder=Path(__file__).resolve().parents[1]/'examples/spikes/controller_firmware'
    for name,build in (('owned_pwm',pwm),('owned_spi_loopback',spi),('owned_i2c_address',i2c)):
        (folder/(name+'.bin')).write_bytes(build())


if __name__=='__main__':main()
