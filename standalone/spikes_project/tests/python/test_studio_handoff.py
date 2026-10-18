# SPDX-License-Identifier: Apache-2.0
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];REPO=ROOT.parents[1];sys.path[:0]=[str(REPO),str(ROOT/'studio/python')]
from python.spike_core.studio_bridge import prepare_spikes_studio_handoff,spikes_studio_launch_arguments
from spikes_studio.studio_handoff import CONTRACT,_record,cross_selection_id,import_handoff_file,validate_handoff
DIGEST='a'*64
def fixture():
 return {'contract':CONTRACT,'source_design':{'digest':DIGEST,'occurrence_id':'main','title':'Board'},'components':[
 {'id':'c1','ref':'R1','value':'10k','placement':{'x_mm':10.,'y_mm':20.,'rotation_deg':45.,'side':'top'},'pins':[{'id':'p1','pin':'1','net_id':'n1','net_name':'VIN','x_mm':9.,'y_mm':20.},{'id':'p2','pin':'2','net_id':'n2','net_name':'OUT','x_mm':11.,'y_mm':20.}],'model_binding':{'status':'reviewed','source_kind':'spike-workspace','model_type':'primitive','primitive':'resistor','value':'10k','pin_bindings':[{'model_pin':'1','pad_id':'p2','circuit_node':'OUT','board_net':'OUT'},{'model_pin':'2','pad_id':'p1','circuit_node':'0','board_net':'VIN'}],'evidence':'confirmed'}},
 {'id':'c2','ref':'U1','value':'IC','placement':{'x_mm':30.,'y_mm':40.,'rotation_deg':12.5,'side':'bottom'},'pins':[{'id':'p3','pin':'IN','net_id':'n1','net_name':'VIN','x_mm':29.,'y_mm':40.},{'id':'p4','pin':'OUT','net_id':'n2','net_name':'OUT','x_mm':31.,'y_mm':40.}],'model_binding':{'status':'unavailable','source_kind':'spike-workspace'}}],
 'nets':[{'id':'n1','name':'VIN','pins':[{'component_id':'c1','pin_id':'p1'},{'component_id':'c2','pin_id':'p3'}]},{'id':'n2','name':'OUT','pins':[{'component_id':'c1','pin_id':'p2'},{'component_id':'c2','pin_id':'p4'}]}], 'wires':[{'net_id':'n1','style':'wire','points_mm':[[9.,20.],[29.,40.]]}],'diagnostics':[]}
class Tests(unittest.TestCase):
 def test_import_and_launch_contract(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);path=prepare_spikes_studio_handoff(fixture(),root);doc=import_handoff_file(path,[path.parent]);parts={p['ref']:p for p in doc.data['components']}
   self.assertIn('R1 OUT 0 10k',doc.data['source']);self.assertNotIn('U1 ',doc.data['source']);self.assertFalse(parts['U1']['execution']['available']);self.assertEqual(parts['U1']['board_placement']['rotation_deg'],12.5)
   self.assertEqual(parts['R1']['cross_selection_id'],cross_selection_id(DIGEST,'main','R1'));self.assertEqual(spikes_studio_launch_arguments(path,root),("--board-circuit-handoff",str(path.resolve())))
 def test_identity_and_path_rejections(self):
  value=fixture();value['components'][0]['cross_selection_id']='wrong'
  with self.assertRaisesRegex(ValueError,'cross_selection'):validate_handoff(value)
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'outside.json';path.write_text(json.dumps(fixture()))
   with self.assertRaisesRegex(ValueError,'inside'):import_handoff_file(path,[Path(td)/'allowed'])
 def test_unavailable_binding_never_becomes_source(self):
  value=fixture();value['components'][0]['model_binding']['status']='unavailable'
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'h.json';path.write_text(json.dumps(value));doc=import_handoff_file(path,[Path(td)])
   self.assertNotIn('R1 OUT 0 10k',doc.data['source'])
 def test_model_pin_order_and_source_alias_are_explicit(self):
  part=validate_handoff(fixture())['components'][0];part['ref']='J1';part['cross_selection_id']=cross_selection_id(DIGEST,'main','J1')
  part['model_binding']['primitive']='voltage_source';part['model_binding']['value']='DC 12';part['model_binding']['model_pins']=['2','1']
  record,reason=_record(part)
  self.assertEqual(reason,'reviewed primitive');self.assertEqual(record['record'].split()[1:4],['0','OUT','DC'])
  self.assertTrue(record['source_ref'].startswith('V'));self.assertNotEqual(record['source_ref'],'J1')
  part['model_binding']['pin_bindings'][0]['circuit_node']='USB Power +'
  part['model_binding']['model_pins']=['1','2'];record,_=_record(part)
  self.assertRegex(record['record'].split()[1],r'^N_[0-9a-f]{16}$')
  part['model_binding']['pin_bindings'][0]['circuit_node']='GND';part['model_binding']['pin_bindings'][1]['circuit_node']='OUT';record,_=_record(part,'GND');self.assertEqual(record['record'].split()[1],'0')
if __name__=='__main__':unittest.main()
