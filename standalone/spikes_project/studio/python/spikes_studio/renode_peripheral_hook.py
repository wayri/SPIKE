# SPDX-License-Identifier: Apache-2.0
"""Original transport-only IronPython helper for explicit owned peripherals."""
import sys
import clr
clr.AddReference('System.IO.Pipes')
from System.IO.Pipes import NamedPipeClientStream, PipeDirection
from System.Text import Encoding


class SpikesPeripheralCollector(sys._spikes_sync_collector_type):
    def __init__(self,machine,ports,capacity,name,token,step_ns):
        sys._spikes_sync_collector_type.__init__(self,machine,ports,True,capacity)
        self.step_ns=step_ns
        self.snapshots={}
        for port in ports:
            gpio=self.device(port)
            self.snapshots[port]=[int(gpio.ReadDoubleWord(offset)) for offset in (0,4,12,8,20,32,36)]
        self.pipe=NamedPipeClientStream('.',name,PipeDirection.InOut)
        self.pipe.Connect(5000)
        self.send('HELLO '+token)
        if self.read()!='OK':raise ValueError('Owned peripheral pipe authentication failed')

    def send(self,text):
        data=Encoding.ASCII.GetBytes(text+'\n')
        self.pipe.Write(data,0,len(data));self.pipe.Flush()

    def read(self):
        chars=[]
        while len(chars)<8192:
            value=self.pipe.ReadByte()
            if value<0:raise ValueError('Owned peripheral pipe closed')
            if value==10:return ''.join(chars)
            if value>127:raise ValueError('Non-ASCII peripheral response')
            chars.append(chr(value))
        raise ValueError('Peripheral response limit')

    def registers(self,port,pin):
        return self.snapshots[port][:]

    def exchange(self,device,write,offset,value,width):
        if self.failed:return 0
        try:
            self.send('%d %d %d %d %d %d' % (self.now(),device,int(write),offset,value,width))
            response=self.read().split()
            if len(response)<2 or response[0]!='OK':raise ValueError('Owned MMIO rejected')
            if device>=3:
                if len(response)!=9:raise ValueError('Incomplete native GPIO snapshot')
                port=chr(ord('A')+device-3)
                values=[int(n) for n in response[2:]]
                if port in self.ports:
                    previous=self.snapshots[port]
                    self.snapshots[port]=values
                    if write and previous!=values:
                        for pin in self.ports[port]:self.append(self.now(),port,pin,values[:])
            return int(response[1])
        except Exception as exc:
            print('SPIKES_MMIO_FAILED '+str(exc))
            self.failed=True
            return 0


sys._spikes_peripheral_collector_type=SpikesPeripheralCollector
