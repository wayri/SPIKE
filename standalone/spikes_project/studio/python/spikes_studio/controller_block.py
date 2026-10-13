"""Trusted C/C++ sampled controller; digest-approved native execution.

Not firmware emulation, an in-process callback, a hostile-code sandbox, or HIL.
State is explicit. Static C variables reset by default and persist only in the
explicit persistent-process mode.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time
from .ide import find_tool

CONTRACT='spikes/generic-controller/v1'
FRESH_PROCESS='fresh_process'
PERSISTENT_PROCESS='persistent_process'
DEFAULT_CODE='''void control_step(double time_s, double step_s, const double *inputs,
                  double *outputs, double *state) {
    /* DI/DO use logical 0/1; AI/AO use volts. Explicit state survives ticks. */
    state[0] += step_s;
    outputs[0] = inputs[0] < 1.0 ? 1.0 : 0.0;
}
'''


def default_config():
    return {'contract':CONTRACT,'language':'C','step_s':1e-4,'state_count':8,'pins':[
        {'name':'sense','mode':'AI','node':'out','reference':'0','source':'','vdd':3.3},
        {'name':'drive','mode':'DO','node':'','reference':'0','source':'V1','vdd':3.3}],
        'source':DEFAULT_CODE}


def validate(config):
    if config.get('contract')!=CONTRACT or config.get('language') not in ('C','C++'):raise ValueError('Controller supports C/C++; Verilog remains in the existing HDL IDE, not this co-simulation bridge')
    if not isinstance(config.get('source'),str) or len(config['source'].encode())>256*1024:raise ValueError('Controller source limit: 256 KiB')
    if type(config.get('step_s')) not in (int,float) or not math.isfinite(config['step_s']) or not 1e-12<=config['step_s']<=1:raise ValueError('Controller step must be 1 ps..1 s')
    if type(config.get('state_count')) is not int or not 1<=config['state_count']<=64:raise ValueError('Controller needs 1..64 explicit state values')
    pins=config.get('pins')
    if not isinstance(pins,list) or not 2<=len(pins)<=64:raise ValueError('Controller requires 2..64 pins')
    names=set();sources=set()
    for pin in pins:
        name=pin.get('name','')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}',name) or name in names or name.startswith('state_') or name in ('time_s','step_s','request_id','ports','state','contract'):raise ValueError('Pin names must be unique safe identifiers, not protocol fields')
        names.add(name)
        if pin.get('mode') not in ('AI','DI','AO','DO'):raise ValueError('Pin modes: AI, DI, AO, DO')
        if type(pin.get('vdd')) not in (int,float) or not math.isfinite(pin['vdd']) or not 0<pin['vdd']<=1000:raise ValueError('Pin VDD must be in (0,1000] V')
        if pin['mode'].endswith('I'):
            for field in ('node','reference'):
                if not re.fullmatch(r'[A-Za-z0-9_.$:/+-]{1,128}',pin.get(field,'')):raise ValueError('Input pin needs valid node/reference names')
        else:
            source=pin.get('source','')
            if not re.fullmatch(r'[Vv][A-Za-z0-9_.$:]+',source) or source.upper() in sources:raise ValueError('Each output needs a unique independent voltage-source binding')
            sources.add(source.upper())
    if not any(p['mode'].endswith('I') for p in pins) or not any(p['mode'].endswith('O') for p in pins):raise ValueError('At least one input and output required')


def _wrapper(config,persistent=False):
    inputs=[p['name'] for p in config['pins'] if p['mode'].endswith('I')];outputs=[p['name'] for p in config['pins'] if p['mode'].endswith('O')]
    states=[f'state_{i}' for i in range(config['state_count'])]
    # Protocol input is produced by CompiledBlockRequest, not arbitrary JSON.
    header=r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "user_code.h"
static char payload[65536];
static double number(const char *key) {
    char token[100]; snprintf(token,sizeof(token),"\"%s\":",key);
    char *p=strstr(payload,token); if(!p) exit(21);
    char *end; double value=strtod(p+strlen(token),&end);
    if(end==p+strlen(token)||!isfinite(value)) exit(22); return value;
}
int main(void) {
'''
    definitions=f'#define INPUT_COUNT {len(inputs)}\n#define OUTPUT_COUNT {len(outputs)}\n#define STATE_COUNT {len(states)}\n'
    definitions+='\n'.join(f'#define IN_{name} {i}' for i,name in enumerate(inputs))+'\n'
    definitions+='\n'.join(f'#define OUT_{name} {i}' for i,name in enumerate(outputs))+'\n'
    header=header.replace('#include "user_code.h"',definitions+'#include "user_code.h"')
    header+=('while(fgets(payload,sizeof(payload),stdin)) {\n' if persistent else 'if(!fgets(payload,sizeof(payload),stdin)) return 20;\n{\n')
    code=header+'char id[129]={0}; char *p=strstr(payload,"\\\"request_id\\\":\\\"");\n'
    code+='if(!p || sscanf(p+14,"%128[^\\\"]",id)!=1) return 23;\n'
    code+=f'double inputs[{len(inputs)}], outputs[{len(outputs)}]={{0}}, state[{len(states)}];\n'
    code+='\n'.join(f'inputs[{i}]=number("{name}");' for i,name in enumerate(inputs))+'\n'
    code+='\n'.join(f'state[{i}]=number("{name}");' for i,name in enumerate(states))+'\n'
    code+='control_step(number("time_s"),number("step_s"),inputs,outputs,state);\n'
    code+='printf("{\\\"contract\\\":\\\"spikes/compiled-block-response/v1\\\",\\\"request_id\\\":\\\"%s\\\",\\\"ports\\\":{",id);\n'
    for i,name in enumerate(outputs):code+=f'printf("{"," if i else ""}\\\"{name}\\\":%.17g",outputs[{i}]);\n'
    code+='printf("},\\\"state\\\":{");\n'
    for i,name in enumerate(states):code+=f'printf("{"," if i else ""}\\\"{name}\\\":%.17g",state[{i}]);\n'
    code+='printf("}}\\n");fflush(stdout);\n}\n'
    return code+('return ferror(stdin) ? 20 : 0;\n}\n' if persistent else 'return 0;\n}\n')


def _strict_response(payload,request,manifest):
    from python.spikes.compiled_blocks import (COMPILED_BLOCK_RESPONSE_CONTRACT,
        CompiledBlockError,CompiledBlockExecutionError,CompiledBlockResponse)
    def reject_constant(value):raise ValueError(f'non-finite constant {value}')
    def reject_duplicates(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    try:value=json.loads(payload.decode('utf-8',errors='strict'),parse_constant=reject_constant,object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError,json.JSONDecodeError,ValueError) as exc:raise CompiledBlockExecutionError('invalid_json_response') from exc
    if not isinstance(value,dict) or set(value)!={'contract','request_id','ports','state'} or value.get('contract')!=COMPILED_BLOCK_RESPONSE_CONTRACT:
        raise CompiledBlockExecutionError('invalid_response_schema')
    try:response=CompiledBlockResponse(request_id=str(value['request_id']),ports=value['ports'],state=value['state'])
    except (CompiledBlockError,TypeError) as exc:raise CompiledBlockExecutionError('invalid_response_schema') from exc
    if response.request_id!=request.request_id:raise CompiledBlockExecutionError('response_request_mismatch')
    if set(response.ports)!=set(manifest.output_ports) or set(response.state)!=set(manifest.state_variables):raise CompiledBlockExecutionError('response_schema_mismatch')
    return response


class Controller:
    def __init__(self,config,*,trusted=False,execution_mode=FRESH_PROCESS):
        validate(config)
        if trusted is not True:raise ValueError('Explicit trusted-code consent is required. Native controller code can access host files/network.')
        if execution_mode not in (FRESH_PROCESS,PERSISTENT_PROCESS):raise ValueError('Controller execution_mode must be fresh_process or persistent_process')
        self.execution_mode=execution_mode;self._closed=False;self._process=None;self._worker_directory=None
        self._request_queue=None;self._response_queue=None;self._reader_stop=threading.Event();self._writer_thread=None;self._stdout_thread=None;self._stderr_thread=None
        self._io_poisoned=False;self._persistent_stderr=bytearray();self._persistent_lock=threading.RLock()
        self.config=deepcopy(config);self.directory=tempfile.TemporaryDirectory(prefix='spikes-controller-');self.path=Path(self.directory.name)
        try:self._compile()
        except Exception:self.close();raise

    def _compile(self):
        from python.spikes.compiled_blocks import CompiledBlockManifest,CompiledBlockApproval,CompiledBlockProcessRuntime,CompiledBlockRuntimeLimits
        cpp=self.config['language']=='C++';tool=find_tool('clang++' if cpp else 'clang') or find_tool('cl')
        if not tool:raise ValueError('No C/C++ compiler configured')
        self.path.joinpath('user_code.h').write_text(self.config['source'],encoding='utf-8')
        wrapper=self.path/('controller.cpp' if cpp else 'controller.c');wrapper.write_text(_wrapper(self.config,self.execution_mode==PERSISTENT_PROCESS),encoding='utf-8')
        self.executable=self.path/('controller.exe' if os.name=='nt' else 'controller')
        env=dict(os.environ);bin_dir=Path(tool).parent
        if Path(tool).stem.lower()=='cl':
            vc=bin_dir.parents[2];sdk=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Windows Kits/10'
            versions=sorted((sdk/'Include').glob('10.*'),reverse=True)
            if not versions:raise ValueError('Windows SDK not found')
            ver=versions[0].name
            env['INCLUDE']=os.pathsep.join([str(vc/'include')]+[str(sdk/'Include'/ver/k) for k in ('ucrt','shared','um')])
            env['LIB']=os.pathsep.join([str(vc/'lib/x64')]+[str(sdk/'Lib'/ver/k/'x64') for k in ('ucrt','um')])
            argv=[tool,'/nologo','/W4','/O2','/TP' if cpp else '/TC','/std:c++20' if cpp else '/std:c17',str(wrapper),'/Fe:'+str(self.executable)]
        else:argv=[tool,'-O2','-Wall','-std=c++20' if cpp else '-std=c17',str(wrapper),'-o',str(self.executable),'-lm']
        with tempfile.TemporaryFile() as log:
            process=subprocess.Popen(argv,cwd=self.path,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:process.wait(timeout=45)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise ValueError('Controller compilation timed out')
            log.seek(0);self.build_log=log.read(1024*1024).decode(errors='replace')
        if process.returncode:raise ValueError('Controller compile failed:\n'+self.build_log)
        self.inputs=[p for p in self.config['pins'] if p['mode'].endswith('I')];self.outputs=[p for p in self.config['pins'] if p['mode'].endswith('O')]
        self.manifest=CompiledBlockManifest.create(block_id='studio.controller',version='1',implementation_language='cpp' if cpp else 'c',executable=self.executable,
            input_ports=[p['name'] for p in self.inputs],output_ports=[p['name'] for p in self.outputs],state_variables=[f'state_{i}' for i in range(self.config['state_count'])],capabilities=['control','stateful','discrete-time'])
        self.approval=CompiledBlockApproval(self.manifest.manifest_sha256,self.manifest.executable_sha256,hashlib.sha256(self.config['source'].encode()).hexdigest(),'interactive user trusted-code consent',True)
        self._limits=CompiledBlockRuntimeLimits();self.runtime=CompiledBlockProcessRuntime([self.approval],self._limits);self.reset()

    def reset(self):
        with self._persistent_lock:
            if self.execution_mode==PERSISTENT_PROCESS:self._stop_persistent()
            self.state={name:0. for name in self.manifest.state_variables};self.tick=0

    def _start_persistent(self):
        from python.spikes.compiled_blocks import COMPILED_BLOCK_REQUEST_CONTRACT,CompiledBlockExecutionError
        if self._closed:raise CompiledBlockExecutionError('controller_closed')
        if self._io_poisoned:raise CompiledBlockExecutionError('process_io_failed')
        if self._process is not None:return
        digest=hashlib.sha256(self.executable.read_bytes()).hexdigest()
        if digest!=self.manifest.executable_sha256:raise CompiledBlockExecutionError('executable_identity_mismatch')
        environment={'SPIKES_COMPILED_BLOCK_PROTOCOL':COMPILED_BLOCK_REQUEST_CONTRACT}
        for key in ('SystemRoot','WINDIR'):
            if key in os.environ:environment[key]=os.environ[key]
        self._worker_directory=tempfile.TemporaryDirectory(prefix='spikes-controller-worker-')
        try:
            self._process=subprocess.Popen([str(self.executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False,
                cwd=self._worker_directory.name,env=environment,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=os.name!='nt')
        except OSError as exc:
            self._worker_directory.cleanup();self._worker_directory=None
            raise CompiledBlockExecutionError('process_start_failed') from exc
        self._request_queue=queue.Queue(maxsize=1);self._response_queue=queue.Queue(maxsize=1);self._reader_stop=threading.Event();self._persistent_stderr=bytearray()
        process=self._process;requests=self._request_queue;responses=self._response_queue;limit=self._limits.max_output_bytes
        def write_stdin():
            assert process.stdin is not None
            while not self._reader_stop.is_set():
                try:job=requests.get(timeout=.1)
                except queue.Empty:continue
                try:process.stdin.write(job['payload']);process.stdin.flush()
                except (BrokenPipeError,OSError) as exc:job['error']=exc
                finally:job['done'].set()
        def send(item):
            while not self._reader_stop.is_set():
                try:responses.put(item,timeout=.1);return
                except queue.Full:pass
        def read_stdout():
            assert process.stdout is not None
            while True:
                line=process.stdout.readline(limit+2)
                if not line:
                    send(('eof',b''));return
                if len(line)>limit or not line.endswith(b'\n'):
                    send(('limit',line[:limit+1]));return
                send(('line',line))
                if self._reader_stop.is_set():return
        def read_stderr():
            assert process.stderr is not None
            while True:
                chunk=process.stderr.read(4096)
                if not chunk:return
                remaining=limit-len(self._persistent_stderr)
                if remaining>0:self._persistent_stderr.extend(chunk[:remaining])
        self._writer_thread=threading.Thread(target=write_stdin,daemon=True,name='spikes-controller-stdin')
        self._stdout_thread=threading.Thread(target=read_stdout,daemon=True,name='spikes-controller-stdout')
        self._stderr_thread=threading.Thread(target=read_stderr,daemon=True,name='spikes-controller-stderr')
        self._writer_thread.start();self._stdout_thread.start();self._stderr_thread.start()

    def _stop_persistent(self):
        process=self._process;self._process=None
        self._reader_stop.set()
        if process is not None:
            if process.poll() is None:
                try:process.terminate();process.wait(timeout=1.)
                except (OSError,subprocess.TimeoutExpired):
                    try:process.kill();process.wait(timeout=1.)
                    except (OSError,subprocess.TimeoutExpired):pass
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream is not None and not stream.closed:
                    try:stream.close()
                    except OSError:pass
        for thread in (self._writer_thread,self._stdout_thread,self._stderr_thread):
            if thread is not None:thread.join(timeout=.2)
        if any(thread is not None and thread.is_alive() for thread in (self._writer_thread,self._stdout_thread,self._stderr_thread)):self._io_poisoned=True
        self._writer_thread=None;self._stdout_thread=None;self._stderr_thread=None;self._request_queue=None;self._response_queue=None
        if self._worker_directory is not None:self._worker_directory.cleanup();self._worker_directory=None

    def _execute_persistent(self,request):
        from python.spikes.compiled_blocks import CompiledBlockExecutionError
        with self._persistent_lock:
            deadline=time.monotonic()+self._limits.timeout_s
            self._start_persistent();process=self._process;requests=self._request_queue;responses=self._response_queue
            assert process is not None and requests is not None and responses is not None
            payload=json.dumps(request.as_dict(),sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()+b'\n'
            if len(payload)>self._limits.max_input_bytes:self._stop_persistent();raise CompiledBlockExecutionError('input_limit_exceeded')
            job={'payload':payload,'done':threading.Event(),'error':None}
            try:requests.put_nowait(job)
            except queue.Full as exc:
                self._stop_persistent();raise CompiledBlockExecutionError('process_io_failed') from exc
            remaining=deadline-time.monotonic()
            if remaining<=0 or not job['done'].wait(remaining):
                self._stop_persistent();raise CompiledBlockExecutionError('process_timeout')
            if job['error'] is not None:
                error=job['error'];self._stop_persistent();raise CompiledBlockExecutionError('process_failed') from error
            remaining=deadline-time.monotonic()
            if remaining<=0:
                self._stop_persistent();raise CompiledBlockExecutionError('process_timeout')
            try:kind,response_payload=responses.get(timeout=remaining)
            except queue.Empty as exc:
                self._stop_persistent();raise CompiledBlockExecutionError('process_timeout') from exc
            if kind!='line':
                returncode=process.poll();self._stop_persistent()
                raise CompiledBlockExecutionError('output_limit_exceeded' if kind=='limit' else ('process_failed' if returncode not in (None,0) else 'process_io_failed'))
            try:return _strict_response(response_payload,request,self.manifest)
            except Exception:self._stop_persistent();raise

    def step(self,values,time_s,step_s):
        with self._persistent_lock:return self._step(values,time_s,step_s)

    def _step(self,values,time_s,step_s):
        from python.spikes.compiled_blocks import CompiledBlockExecutionError,CompiledBlockRequest
        if self._closed:raise CompiledBlockExecutionError('controller_closed')
        pins={p['name']:float(values[p['name']]) for p in self.inputs}
        for p in self.inputs:
            if p['mode']=='DI':pins[p['name']]=float(pins[p['name']]>=p['vdd']/2)
        request=CompiledBlockRequest(f'tick_{self.tick}',time_s,step_s,pins,self.state)
        response=self._execute_persistent(request) if self.execution_mode==PERSISTENT_PROCESS else self.runtime.execute(self.manifest,self.executable,request)
        voltages={}
        try:
            for p in self.outputs:
                value=response.ports[p['name']]
                if p['mode']=='DO':
                    if value not in (0.,1.):raise ValueError('Digital output must be 0 or 1')
                    value*=p['vdd']
                elif not -p['vdd']<=value<=p['vdd']:raise ValueError('Analog output exceeds configured ±VDD envelope')
                voltages[p['source']]=value
        except Exception:
            if self.execution_mode==PERSISTENT_PROCESS:self._stop_persistent()
            raise
        self.state=dict(response.state);self.tick+=1;return voltages

    def bind(self,project):
        from python.spikes.native_runner import _nodes
        nodes=set(_nodes(project));sources={e.name:e for e in project.elements if e.kind=='voltage_source' and e.waveform is None}
        for pin in self.inputs:
            if pin['node'] not in nodes or pin['reference'] not in nodes:raise ValueError('Controller input references a missing node')
        for pin in self.outputs:
            if pin['source'] not in sources:raise ValueError('Controller output must bind an existing independent DC voltage source (exact name)')
        if project.analysis.time_step_s is None:raise ValueError('Controller coupling requires .tran')
        ratio=self.config['step_s']/project.analysis.time_step_s
        if ratio<1 or abs(ratio-round(ratio))>1e-8:raise ValueError('Controller tick must be an integer multiple of the circuit output timestep')
        self.stride=round(ratio);self.reset()

    def advance(self,session):
        # Native session exposes no electrical values before its first accepted
        # point. Boot output is the source's netlist value, not invented sensing.
        if session.step_index==0:return {}
        if session.step_index%self.stride:return {}
        values={p['name']:session.node_voltage(p['node'])-session.node_voltage(p['reference']) for p in self.inputs}
        outputs=self.step(values,session.time_s,self.config['step_s'])
        for source,value in outputs.items():session.set_source_value(source,value)
        return outputs

    @property
    def runtime_stderr(self):return bytes(self._persistent_stderr).decode(errors='replace')

    def close(self):
        with self._persistent_lock:
            self._closed=True;self._stop_persistent()
            if getattr(self,'directory',None) is not None:self.directory.cleanup();self.directory=None
