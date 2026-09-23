from pathlib import Path
import sys
import unittest
from copy import deepcopy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.dashboard import *

class DashboardTests(unittest.TestCase):
    def test_layout_validation_and_updates(self):
        data=empty_dashboard();row=widget('Meter','v(out)');data['widgets'].append(row)
        changed=update_widget(data,row['id'],x=80,width=320)
        self.assertEqual(data['widgets'][0]['x'],20);self.assertEqual(changed['widgets'][0]['x'],80)
        self.assertEqual(snap(31),40);self.assertEqual(snap(-10),0)
    def test_rejects_invalid_layout(self):
        data=empty_dashboard();data['widgets'].append(widget('Scope'))
        for key,value in [('width',10),('x',-1),('minimum',float('nan')),('maximum',0),('kind','Hardware relay')]:
            with self.assertRaises(ValueError):update_widget(data,data['widgets'][0]['id'],**{key:value})
        duplicate=deepcopy(data);duplicate['widgets']*=2
        with self.assertRaises(ValueError):validate_dashboard(duplicate)
    def test_no_synthetic_reading(self):
        with self.assertRaises(ValueError):read_signal(None,'v(out)')
        class Engine:
            time=np.array([0.,1.,2.])
            def evaluate(self,expr):
                class Q:values=np.array([1.,2.,3.]);unit='V'
                return Q()
        time,values,unit=read_signal(Engine(),'v(out)');self.assertEqual(values[-1],3);self.assertEqual(unit,'V')
    def test_layout_undo_save(self):
        from spikes_studio.document import Document,RC_DECK
        d=Document.from_netlist(RC_DECK);data=empty_dashboard();data['widgets'].append(widget('Indicator','v(out)'))
        d.commit(lambda state:state.update(dashboard=data));self.assertEqual(len(d.data['dashboard']['widgets']),1)
        d.undo();self.assertEqual(d.data.get('dashboard',empty_dashboard())['widgets'],[])
    def test_scope_uses_time_not_sample_index(self):
        bins=scope_bins([0,.01,.02,.03,9.9,10],[0,0,9,0,1,2],10)
        self.assertEqual(bins[0],(0,0.,9.));self.assertEqual(bins[-1],(9,1.,2.))
        with self.assertRaises(ValueError):scope_bins([0,2,1,3],[0,0,0,0],10)

if __name__=='__main__':unittest.main()
