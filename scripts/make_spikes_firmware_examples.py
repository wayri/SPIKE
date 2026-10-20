# SPDX-License-Identifier: Apache-2.0
"""Generate original, minimal Cortex-M GPIO echo smoke firmware (no SDK).

The exact independently authored Thumb instructions are recorded below.
This is a functional emulator fixture, not production board firmware.
"""
from pathlib import Path
import struct
import sys


def gpio_echo(stm=False, *, uart=True):
    flash=0x08000000 if stm else 0
    data=bytearray(0x100);literals=[];labels={};branches=[]
    struct.pack_into('<II',data,0,0x20020000 if stm else 0x20040000,flash+0x101)
    def emit(word):data.extend(struct.pack('<H',word))
    def literal(register,value):literals.append((len(data),register,value));emit(0)
    def write(address,value):
        literal(0,address)
        if value<=255:emit(0x2100|value)  # movs r1,#value
        else:literal(1,value)
        emit(0x6001)  # str r1,[r0]
    def branch(label,conditional=False):branches.append((len(data),label,conditional));emit(0)
    base=0x40020400 if stm else 0x50000500
    if stm:write(0x40023830,2)  # RCC_AHB1ENR GPIOBEN
    write(base if stm else base+0x14,64 if stm else 8)
    if not stm:
        write(0x50000708,0);write(0x5000070c,1)  # connected input / push-pull output
    if not stm and uart:
        # UART register datapath only: this engine does not model pad pin-mux.
        # Do not claim the UART capture establishes physical routed-pin behavior.
        write(0x40002524,0x00275000)  # BAUDRATE 9600
        write(0x40002500,8)  # UARTE ENABLE (EasyDMA)
        write(0x40002534,0x20000000);write(0x40002538,1)  # RXD PTR / MAXCNT
        write(0x40002544,0x20000000);write(0x40002548,1)  # TXD PTR / MAXCNT
        write(0x40002000,1)  # STARTRX
    labels['loop']=len(data)
    literal(0,base+0x10);emit(0x6802)  # ldr r2,[r0] (IN)
    emit(0x2304);emit(0x401a);emit(0x0052)  # mask bit2, shift to bit3
    if stm:
        # Use atomic BSRR, preserving externally driven input bits. Whole-port
        # ODR writes in the reviewed emulator also modify its input latch.
        emit(0x2a00);branch('low',True)  # cmp r2,#0 ; beq low
        write(base+0x18,8);branch('loop')
        labels['low']=len(data);write(base+0x18,0x80000)
    else:
        literal(0,base+4);emit(0x6002)  # store OUT
    if not stm and uart:
        literal(0,0x40002110);emit(0x6801);emit(0x2900)  # ENDRX; cmp r1,#0
        branch('loop',True)
        emit(0x2100);emit(0x6001)  # clear event
        write(0x40002008,1);write(0x40002000,1)  # transmit received RAM byte, rearm RX
    branch('loop')
    while len(data)%4:data.append(0)
    for position,register,value in literals:
        offset=len(data)-((position+4)&~3)
        assert offset%4==0 and 0<=offset//4<=255
        struct.pack_into('<H',data,position,0x4800|(register<<8)|(offset//4))
        data.extend(struct.pack('<I',value))
    for position,label,conditional in branches:
        offset=(labels[label]-position-4)//2
        assert -128<=offset<=127
        struct.pack_into('<H',data,position,(0xd000|(offset&255)) if conditional else (0xe000|(offset&2047)))
    return bytes(data)


def main():
    target=Path(__file__).resolve().parents[1]/'examples/spikes/controller_firmware'
    target.mkdir(parents=True,exist_ok=True)
    (target/'nrf52840_gpio_echo.bin').write_bytes(gpio_echo())
    (target/'nrf52840_gpio_only_echo.bin').write_bytes(gpio_echo(uart=False))
    (target/'stm32f407_gpio_echo.bin').write_bytes(gpio_echo(True))
    sys.path.insert(0,str(target.parents[2]/'standalone/spikes_project/studio/python'))
    sys.path.insert(0,str(target.parents[2]))
    from spikes_studio.document import Document
    from spikes_studio.controller_boards import get_record
    from spikes_studio.controller_board_blocks import create,add
    doc=Document.from_netlist('Firmware GPIO-controlled RC\nVSENSE sense 0 0\nVDRIVE drive 0 0\nR1 drive out 1k\nC1 out 0 1u\n.tran 100u 10m uic\n.end\n')
    block=create(get_record('st-stm32f407g-disc1-mb997'),1000,100)
    for label,mode in (('PB2','DI'),('PB3','DO')):
        pin=next(pin for pin in block['board']['pins'] if pin['label']==label)
        block['bindings'][pin['id']].update(mode=mode,node='sense' if mode=='DI' else '',reference='0' if mode=='DI' else '',source='VDRIVE' if mode=='DO' else '')
    add(doc,block);doc.save(target/'stm32f407_gpio_rc.spksch')


if __name__=='__main__':main()
