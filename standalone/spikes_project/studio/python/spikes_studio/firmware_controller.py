# SPDX-License-Identifier: Apache-2.0
"""Explicit DI/DO zero-order-held firmware / native-circuit adapter.

No analog ADC/DAC, tristate resolution, pad current, pin parasitics, SPI/I2C
wire timing, or RF propagation is inferred from a firmware board template.
"""
from copy import deepcopy
import hashlib
import json
import math
from types import SimpleNamespace
from .controller_block import Controller
from .controller_board_blocks import controller_config
from .firmware_session import FirmwareSession,gpio_pin


class FirmwareController:
    close_after_run=True
    event_origin='firmware_gpio'

    def __init__(self,block,runtime,image,*,step_s=1e-4,trusted=False,expected_sha256=None):
        self.block=deepcopy(block)
        self.config=controller_config(block,step_s=step_s)
        if step_s<1e-9 or abs(round(step_s*1e9)/1e9-step_s)>1e-15:
            raise ValueError('Firmware sampling interval must be an integer number of nanoseconds')
        if any(p['mode'] not in ('DI','DO') for p in self.config['pins']):
            raise ValueError('Firmware circuit coupling supports DI/DO only; ADC/DAC voltage conversion is not implemented')
        self.inputs=[p for p in self.config['pins'] if p['mode']=='DI']
        self.outputs=[p for p in self.config['pins'] if p['mode']=='DO']
        board=block['board'];self.mapping={}
        for pin in board['pins']:
            binding=block['bindings'][pin['id']]
            if binding['mode']!='NC':self.mapping[binding['code_name']]=gpio_pin(board['id'],pin)
        if len(set(self.mapping.values()))!=len(self.mapping):raise ValueError('Two connector positions alias the same MCU GPIO; bind it only once')
        self.session=FirmwareSession(runtime,image,board['id'],trusted=trusted,expected_sha256=expected_sha256)
        evidence={**self.session.provenance(),'pins':self.config['pins'],'step_s':step_s}
        self.manifest=SimpleNamespace(manifest_sha256=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest())
        self._closed=False

    def reset(self):
        if self.session.time_ns!=0 or self._closed:raise ValueError('Firmware circuit runs require a fresh approved session; load again')

    def bind(self,project):
        # Reuse the existing exact-node/source and integer-stride contract.
        Controller.bind(self,project)

    def step(self,values,time_s,step_s):
        for pin in self.inputs:
            value=float(values[pin['name']])
            if not math.isfinite(value):raise ValueError('Nonfinite firmware input voltage')
            port,index=self.mapping[pin['name']]
            self.session.set_gpio(port,index,value>=pin['vdd']/2)
        self.session.run_for(step_s)
        # Keep the native UART writer bounded even when there is no open UART
        # window. The bridge does not claim to expose a UART circuit model.
        self.session.uart_read()
        voltages={}
        for pin in self.outputs:
            port,index=self.mapping[pin['name']]
            voltages[pin['source']]=pin['vdd'] if self.session.output_level(port,index) else 0.
        return voltages

    def advance(self,session):return Controller.advance(self,session)

    def provenance(self):
        return {**self.session.provenance(),'manifest_sha256':self.manifest.manifest_sha256,
                'step_s':self.config['step_s'],'board_block_id':self.block['id'],
                'semantics':'sampled DI/DO feedback; VDD/2 threshold; zero-order-held independent voltage sources; first tick after accepted plant point',
                'bindings':deepcopy(self.config['pins'])}

    def close(self):
        self._closed=True;self.session.close()
