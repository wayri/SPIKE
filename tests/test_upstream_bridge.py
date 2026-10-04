# SPDX-License-Identifier: Apache-2.0
"""Bridge result admission using independent public-object fixtures, no FEM."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import tempfile
import types
import unittest
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ScriptViews = runpy.run_path(str(ROOT/'python/spike_core/script_views.py'))['ScriptViews']

SOURCE = '''import emerge as em
import numpy as np
model=em.Simulation('fixture')
model.view()
class FieldPlotData:
    x=np.array([0.,1.,2.,3.])
    y=np.zeros(4)
    z=np.zeros(4)
    F=np.array([1+2j,3+4j,5+6j,np.nan+0j])
    vx=vy=vz=None
class Field:
    freq=3e9+0j
    def scalar(self,name,representation):return FieldPlotData()
class Grid:
    freq=np.array([3e9])
    def S(self,out_port,in_port):
        if out_port>2 or in_port>2:raise KeyError('no port')
        return np.array([complex(out_port/10,in_port/10)])
class Scalar:
    @property
    def grid(self):return Grid()
class Data:
    scalar=Scalar()
    field=[Field(),Field()]
data=Data()
model.display.add_field(data.field[0].scalar('Ey','complex'))
model.display.show()
'''


class Display:
    def add_field(self,*args,**kwargs):raise AssertionError('native upstream display called')
    def add_farfield3d(self,*args,**kwargs):raise AssertionError('native upstream far-field display called')
    def show(self):raise AssertionError('native upstream window called')


class Model:
    display=Display()
    def __init__(self,*args):pass
    def view(self):raise AssertionError('native upstream window called')


class BridgeTests(unittest.TestCase):
    def geometry_fixture(self):
        material=lambda name:types.SimpleNamespace(name=name)
        geometry=lambda name,dim,tags,mat:types.SimpleNamespace(name=name,dim=dim,tags=tags,dimtags=[(dim,t) for t in tags],material=material(mat) if mat else None)
        geos=[geometry('substrate',3,[1],'FR4'),geometry('air',3,[2],'Air'),geometry('patch',2,[11],'PEC'),geometry('port',2,[13],None)]
        class GeometryModel(Model):
            def generate_mesh(self):pass
            def all_geos(self):return geos
        triangles={10:[1,2,3],11:[1,3,4],12:[5,6,7],13:[1,2,4]}
        mesh=types.SimpleNamespace(getNodes=lambda:(np.arange(1,8),np.array([[0,0,-.001],[.1,0,-.001],[.1,.1,0],[0,.1,0],[9,9,9],[10,9,9],[9,10,9]]).reshape(-1),[]),getElements=lambda dim,tag:([2],[],[triangles[tag]]),getElementProperties=lambda typ:('triangle',2,1,3,[],3))
        gmsh=types.SimpleNamespace(model=types.SimpleNamespace(mesh=mesh,getBoundary=lambda tags,**kwargs:[(2,10),(2,11)] if tags==[(3,1)] else [(2,12)]))
        return GeometryModel,gmsh

    def run_fixture(self,source=SOURCE,options=None,model=Model,gmsh=None,parameters=None,defaults=None):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            pack=root/'pack';(pack/'source/examples').mkdir(parents=True)
            path=pack/'source/examples/fixture.py';path.write_text(source)
            (pack/'bridge.py').write_bytes((ROOT/'examples/upstream-emerge/bridge.py').read_bytes())
            (pack/'scene_capture.py').write_bytes((ROOT/'examples/upstream-emerge/scene_capture.py').read_bytes())
            (pack/'manifest.json').write_text(json.dumps({'commit':'independent-test-fixture','examples':[{'path':'examples/fixture.py','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'suspended':False,'defaults':defaults or {}}]}))
            original_version=importlib.metadata.version
            version=lambda package:'3.0.0a19' if package=='emerge' else original_version(package)
            api=ScriptViews()
            import os
            previous=Path.cwd()
            try:
                os.chdir(root)
                modules={'emerge':types.SimpleNamespace(Simulation=model)}
                if gmsh is not None:modules['gmsh']=gmsh
                with patch.dict('sys.modules',modules),patch('importlib.metadata.version',version):
                    runpy.run_path(str(pack/'bridge.py'))['run_example']('examples/fixture.py',parameters or {},api,options)
                artifacts=json.loads((root/'artifacts/upstream-emerge/fixture/field-manifest.json').read_text())
                for group in ('fields','meshes','farfields'):
                    for entry in artifacts[group]:
                        if 'file' not in entry:continue
                        artifact=root/'artifacts/upstream-emerge/fixture'/entry['file']
                        self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(),entry['sha256'])
                        if group=='farfields':
                            with np.load(artifact) as stored:
                                entry['_arrays']={key:stored[key].copy() for key in stored.files}
            finally:
                os.chdir(previous)
            return api.views,artifacts

    def test_preserves_complex_samples_and_all_available_ports(self):
        views,artifacts=self.run_fixture()
        field=next(v for v in views if v['kind']=='spatial')
        self.assertEqual(field['quantity'],'Ey')
        self.assertEqual(field['value_unit'],'V/m')
        self.assertEqual(len(field['samples']),3)
        self.assertEqual(field['samples'][1]['value_real'],3)
        self.assertEqual(field['samples'][1]['value_imag'],4)
        table=next(v for v in views if v['title']=='Actual upstream scattering samples')
        self.assertEqual({tuple(row[1:3]) for row in table['rows']},{(1,1),(1,2),(2,1),(2,2)})
        self.assertEqual(artifacts['fields'][0]['returned_samples'],4)

    def test_eigenmode_unstructured_grid_keeps_frequencies(self):
        source=SOURCE.replace('def grid(self):return Grid()',"def grid(self):raise ValueError('unstructured eigenmodes')")
        views,_=self.run_fixture(source)
        table=next(v for v in views if v['title']=='Returned field solution frequencies')
        self.assertEqual(table['rows'],[[0,3e9,0],[1,3e9,0]])
        self.assertEqual(sum(v['kind']=='spatial' for v in views),1)

    def test_preview_cap_preserves_full_sidecars(self):
        source=SOURCE.replace("model.display.show()","for i in range(5):model.display.add_field(data.field[0].scalar('Ey','complex'))\nmodel.display.show()")
        views,artifacts=self.run_fixture(source)
        self.assertEqual(sum(v['kind']=='spatial' for v in views),3)
        self.assertEqual(len(artifacts['fields']),6)

    def test_axis_reference_decorations_are_not_frequency_samples(self):
        source=SOURCE+"\nimport matplotlib.pyplot as plt\nfig,ax=plt.subplots()\nax.plot([1.,2.,3.],[3.,2.,1.],label='sampled curve')\nax.axhline(.5,label='axis reference')\nax.set_xlabel('Frequency (GHz)')\n"
        views,_=self.run_fixture(source)
        curves=[v for v in views if v['kind']=='line']
        self.assertEqual(len(curves),1)
        self.assertEqual(curves[0]['x'],[1.,2.,3.])
        self.assertEqual(curves[0]['x_label'],'Frequency (GHz)')
        self.assertEqual(curves[0]['x_unit'],'')

    def test_farfield_capture_preserves_angles_gain_and_nonphysical_display_scale(self):
        source=SOURCE+'''\nclass Gain:\n    norm=np.array([[1.,.5],[.25,.125]])\nclass Farfield:\n    theta=np.array([[0.,np.pi/2],[np.pi/2,np.pi]])\n    phi=np.array([[0.,0.],[np.pi/2,np.pi]])\n    gain=Gain()\n    freq=3e9\nField.farfield_3d=lambda self,*args,**kwargs:Farfield()\nff=data.field[0].farfield_3d(None,origin=(.01,.02,.03))\nmodel.display.add_farfield3d(ff,rmax=.04,offset=(.1,.2,.3),dBfloor=-20)\n'''
        views,artifacts=self.run_fixture(source)
        view=next(v for v in views if v.get('quantity')=='directional gain')
        self.assertEqual(view['value_unit'],'dBi')
        self.assertEqual(view['coordinate_unit'],'m')
        self.assertEqual(len(view['samples']),4)
        self.assertAlmostEqual(view['samples'][0]['z'],.07)
        self.assertAlmostEqual(view['samples'][0]['x'],.01)
        self.assertAlmostEqual(view['samples'][1]['value_real'],20*np.log10(.5))
        provenance=json.loads(view['provenance'])
        self.assertIn('not an observation distance',provenance['display_mapping'])
        self.assertEqual(provenance['source_origin_m'],[.01,.02,.03])
        self.assertEqual(provenance['scene_role'],'farfield_pattern')
        self.assertEqual(provenance['scene_id'],json.loads(next(v for v in views if v.get('quantity')=='Ey')['provenance'])['scene_id'])
        entry=artifacts['farfields'][0]
        np.testing.assert_allclose(entry['_arrays']['theta_rad'],[0.,np.pi/2,np.pi/2,np.pi])
        np.testing.assert_allclose(entry['_arrays']['gain_amplitude_ratio'],[1.,.5,.25,.125])
        self.assertEqual(entry['returned_samples'],4)
        self.assertEqual(entry['angle_unit'],'rad')

    def test_radiation_curves_are_reserved_inside_six_curve_limit(self):
        source=SOURCE+'''\nimport matplotlib.pyplot as plt\nfig,ax=plt.subplots()\nfor i in range(7):ax.plot([1.,2.,3.],[i+1.,i+2.,i+3.],label='network '+str(i))\npolar=plt.figure().add_subplot(projection='polar')\npolar.plot([0.,1.,2.],[1.,2.,1.],label='gain cut A')\npolar.plot([0.,1.,2.],[2.,3.,2.],label='gain cut B')\n'''
        views,_=self.run_fixture(source)
        plots=[view for view in views if view['kind'] in ('line','polar')]
        self.assertEqual(len(plots),6)
        priorities=[json.loads(view['provenance'])['radiation_priority'] for view in plots]
        self.assertEqual(priorities.count(True),2)
        self.assertEqual(priorities.count(False),4)
        self.assertIn('gain cut A',plots[0]['title'])

    def test_geometry_preparation_preserves_complete_physical_faces_and_stops_before_solve(self):
        model,gmsh=self.geometry_fixture()
        source="import emerge as em\nmodel=em.Simulation('fixture')\nmodel.generate_mesh()\nraise AssertionError('solve must not run')\n"
        views,artifacts=self.run_fixture(source,{'geometry_only':True},model,gmsh)
        self.assertEqual(len(views),1)
        mesh=views[0]
        self.assertEqual(len(mesh['triangles']),2)
        self.assertEqual(len(mesh['vertices']),4)
        self.assertLess(max(max(v) for v in mesh['vertices']),1)
        provenance=json.loads(mesh['provenance'])
        self.assertEqual(provenance['phase'],'geometry')
        self.assertEqual(provenance['scene_role'],'physical_geometry')
        self.assertEqual([(r['material'],r['triangle_count']) for r in provenance['regions']],[('FR4',1),('PEC',1)])
        self.assertEqual(len(artifacts['meshes'][0]['excluded']),2)

    def test_prepare_and_solve_share_scene_but_have_distinct_runs(self):
        model,gmsh=self.geometry_fixture()
        source=SOURCE.replace("model.view()","model.generate_mesh()")
        prepared,_=self.run_fixture(source,{'geometry_only':True},model,gmsh)
        solved,_=self.run_fixture(source,None,model,gmsh)
        a=json.loads(prepared[0]['provenance'])
        b=json.loads(solved[0]['provenance'])
        field=json.loads(next(view for view in solved if view['kind']=='spatial')['provenance'])
        self.assertEqual(a['scene_id'],b['scene_id'])
        self.assertNotEqual(a['run_id'],b['run_id'])
        self.assertEqual(b['run_id'],field['run_id'])
        self.assertEqual(b['coordinate_frame'],field['coordinate_frame'])

    def test_unknown_farfield_origin_does_not_invent_aligned_samples(self):
        source=SOURCE+"\nff=type('FF',(),{'theta':np.array([0.]),'phi':np.array([0.]),'gain':type('Gain',(),{'norm':np.array([1.])})()})()\nmodel.display.add_farfield3d(ff,rmax=.04)\n"
        views,artifacts=self.run_fixture(source)
        self.assertFalse(any(v.get('quantity')=='directional gain' for v in views))
        self.assertEqual(len(artifacts['farfields']),1)
        self.assertIn('origin unavailable','; '.join(artifacts['diagnostics']))

    def test_geometry_only_refuses_solver_before_any_mesh(self):
        class SolverModel(Model):
            def run_sweep(self):raise AssertionError('solver must not be called')
        with self.assertRaisesRegex(RuntimeError,'before explicit mesh preparation'):
            self.run_fixture("import emerge as em\nmodel=em.Simulation('fixture')\nmodel.run_sweep()",{'geometry_only':True},SolverModel)

    def test_changed_effective_parameter_invalidates_scene_identity(self):
        source='width=1.0\n'+SOURCE
        first,_=self.run_fixture(source,defaults={'width':1.0})
        second,_=self.run_fixture(source,parameters={'width':2.0},defaults={'width':1.0})
        self.assertNotEqual(json.loads(first[0]['provenance'])['scene_id'],json.loads(second[0]['provenance'])['scene_id'])


if __name__=='__main__':unittest.main()
