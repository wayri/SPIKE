from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.waveform_index import WaveformIndex


class WaveformIndexTests(unittest.TestCase):
    def test_extrema_endpoints_bounds_and_memory(self):
        time=np.arange(100003,dtype=float);values=np.sin(time*.1)
        values[1]=50;values[99999]=-90;values[50123]=80
        index=WaveformIndex(time,values)
        self.assertLess(index.cache_bytes,values.nbytes/40)
        for limits in (None,(0,100002),(40000,80000),(50120,50125),(0,3),(99995,100004),(123.5,92000.7)):
            picked=index.indices(limits,128)
            self.assertLessEqual(len(picked),128)
            self.assertTrue(np.all(np.diff(picked)>0))
            left,right=(0,len(time)) if limits is None else (max(0,np.searchsorted(time,min(limits))-1),min(len(time),np.searchsorted(time,max(limits),side='right')+1))
            self.assertEqual(picked[0],left);self.assertEqual(picked[-1],right-1)
            self.assertEqual(values[picked].min(),values[left:right].min())
            self.assertEqual(values[picked].max(),values[left:right].max())
        self.assertEqual(values[50123],80)

    def test_small_empty_and_invalid(self):
        for count in (0,1,7,256,257,512):
            index=WaveformIndex(np.arange(count),np.zeros(count))
            self.assertLessEqual(len(index.indices(budget=8)),8)
        with self.assertRaises(ValueError):WaveformIndex([1,2],[1])
        with self.assertRaises(ValueError):WaveformIndex([1],[1j])
        index=WaveformIndex([0,1],[1,2])
        with self.assertRaises(ValueError):index.indices((float('nan'),1))
