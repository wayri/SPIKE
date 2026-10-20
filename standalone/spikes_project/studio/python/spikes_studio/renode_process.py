# SPDX-License-Identifier: Apache-2.0
"""Bounded pipe-only adapter to the separately installed Renode 1.17.0 engine.

Monitor interface: https://renode.readthedocs.io/en/latest/basic/running.html
No TCP monitor, UART socket, shell, user script or network bridge is opened.
Process isolation is crash containment, not a hostile-code sandbox.
"""
from collections import deque
import hashlib
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time
import uuid

EXE_SHA256 = '67c2c21eb977181a50a19acbf582c4204d8177d2b4ae0bac4c3d3d51da7a7b4e'
ARCHIVE_SHA256 = '18bcf145422039e8702c3e5f9864c7787561bfd5deb7a3ee6e168ecf19e2b9db'
SOURCE_URL = 'https://github.com/renode/renode/releases/download/v1.17.0/renode-1.17.0.windows-portable.zip'
# The native console briefly exclusively opens its history file at startup.
# Serialize constructors inside Studio; separate processes must also serialize
# integration tests until the backend offers per-process history isolation.
_STARTUP_LOCK = threading.Lock()


def find_runtime():
    explicit = os.environ.get('SPIKES_RENODE')
    if explicit:return Path(explicit)
    base = Path(os.environ.get('LOCALAPPDATA',str(Path.home())))
    installed = base/'Programs/SPIKES Studio Runtimes/Renode-1.17.0/Renode.exe'
    if installed.is_file():return installed
    for parent in Path(__file__).resolve().parents:
        candidate = parent/'runtime/external/renode-1.17.0/renode_1.17.0-portable/Renode.exe'
        if candidate.is_file():return candidate
    return None


def runtime_digest(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest != EXE_SHA256:raise ValueError('Only the reviewed Windows Renode 1.17.0 executable is admitted')
    return digest


class RenodeProcess:
    def __init__(self,path,*,trusted=False,timeout_s=20):
        if not trusted:raise ValueError('Explicit runtime / firmware trust approval is required')
        self.path=Path(path).resolve(strict=True);self.digest=runtime_digest(self.path)
        if not 1<=timeout_s<=60:raise ValueError('Runtime timeout must be 1..60 seconds')
        self.timeout_s=timeout_s;self.lock=threading.RLock();self.lines=queue.Queue(maxsize=4096)
        self.history=deque(maxlen=1000);self.overflow=threading.Event();self.closed=False
        self.directory=tempfile.TemporaryDirectory(prefix='spikes-firmware-')
        self.work=Path(self.directory.name)
        with _STARTUP_LOCK:
            self.process=subprocess.Popen([str(self.path),'--disable-gui','--console','--plain','-P','-1',
                '--config',str(self.work/'renode.config')],cwd=self.path.parent,stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.reader=threading.Thread(target=self._read,daemon=True,name='spikes-renode-reader');self.reader.start()
            try:
                version=self.command('version')
                if 'version 1.17.0' not in version:raise ValueError('Renode version handshake mismatch')
            except BaseException:self.close();raise

    def _read(self):
        try:
            while True:
                line=self.process.stdout.readline(65537)
                if not line:break
                if len(line)>65536:raise ValueError('Emulator line limit')
                self.lines.put_nowait(line.decode('utf-8',errors='replace'))
        except (ValueError,queue.Full):
            self.overflow.set();self.process.terminate()
        finally:
            try:self.lines.put_nowait(None)
            except queue.Full:pass

    def command(self,command):
        with self.lock:
            if self.closed or self.process.poll() is not None:raise RuntimeError('Firmware runtime is closed')
            if not isinstance(command,str) or len(command)>16384 or any(c in command for c in '\r\n\0'):
                raise ValueError('Invalid internal emulator command')
            token='SPIKES_ACK_'+uuid.uuid4().hex
            self.process.stdin.write((command+'\nlog "'+token+'"\n').encode('utf-8'));self.process.stdin.flush()
            deadline=time.monotonic()+self.timeout_s;result=[];size=0
            try:
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('Firmware command timed out')
                    try:line=self.lines.get(timeout=remaining)
                    except queue.Empty:raise TimeoutError('Firmware command timed out') from None
                    if self.overflow.is_set():raise RuntimeError('Emulator output limit exceeded')
                    if line is None:raise RuntimeError('Firmware runtime exited unexpectedly')
                    if re.search(r'\[INFO\]\s+Script:\s*'+token+r'\s*$',line):break
                    size+=len(line)
                    if size>256*1024:raise RuntimeError('Firmware response exceeds 256 KiB')
                    result.append(line);self.history.append(line.rstrip())
                text=''.join(result)
                if re.search(r'There was an error|No such command|\[ERROR\]|Unhandled (read|write)|non existing peripheral|CPU abort',text,re.I):
                    raise RuntimeError('Emulator rejected execution: '+text[-3000:])
                return text
            except BaseException:
                self.close();raise

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True
            if self.process.poll() is None:
                try:self.process.stdin.write(b'quit\n');self.process.stdin.flush();self.process.wait(timeout=2)
                except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait(timeout=5)
            for stream in (self.process.stdin,self.process.stdout):
                try:stream.close()
                except OSError:pass
            self.reader.join(timeout=2)
            self.directory.cleanup()
