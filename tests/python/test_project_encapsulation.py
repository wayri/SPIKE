# SPDX-License-Identifier: Apache-2.0
"""Actual encapsulant STEP retention, identity and regeneration regression."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from tests.python.test_assembly_thermal_encapsulation import encapsulated
from tests.python.test_assembly_thermal_meshing import has_runtime
from tests.python.test_project_assembly_field import _payload, MODEL_ARTIFACT
from python.spike_core.project_package import read_project, write_spike_package, ProjectPackageError
from python.spike_core.service_project_thermal_mesh import run_assembly_thermal_mesh_in_project, _artifact_reader
from python.spike_core.service_project_encapsulation import retain_generated_encapsulation
from python.spike_core.assembly_thermal_meshing import run_assembly_thermal_mesh
from python.spike_core.service_project_assembly_field import _assembly_identity, read_assembly_field_study_in_project
from python.spike_core.multiboard_study import physical_assembly


def package_fixture(path, kind='coating'):
    p,a,o,r=encapsulated(kind)
    payload=_payload({'assembly':p['assembly_ir']})
    p['design_ir']['source']['source_format']='spike-fixture'
    payload['design_ir'].update(p['design_ir'])
    manifest=write_spike_package(path,payload,model_artifacts={'original-case.step':MODEL_ARTIFACT},
        preserved_members={'sources/board.kicad_pcb':r('unused'),'reports/artifacts/unrelated.txt':b'keep this report'})
    params={'project_path':str(path),'expected_manifest_payload_sha256':manifest['manifest_payload_sha256'],
            'assignments':a,'mesh_options':o}
    return params


@unittest.skipUnless(has_runtime(),'Requires admitted local OCC runtime')
class ProjectEncapsulationTests(unittest.TestCase):
    def _assert_project_generation(self,kind,expected_volume):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'study.spike';params=package_fixture(path,kind)
            before=read_project(path,include_members=True)
            result=run_assembly_thermal_mesh_in_project(params,application_version='test')
            self.assertEqual(result['status'],'completed',result.get('blockers'))
            self.assertTrue(result['project_updated'])
            opened=read_project(path,include_members=True)
            self.assertEqual(opened.members['reports/artifacts/unrelated.txt'],b'keep this report')
            self.assertEqual(opened.members['models/artifacts/original-case.step'],MODEL_ARTIFACT)
            self.assertEqual(opened.members['sources/board.kicad_pcb'],before.members['sources/board.kicad_pcb'])
            self.assertEqual(physical_assembly(result['request']['assembly']),physical_assembly(opened.payload['assembly_ir']))
            source=result['encapsulation_sources'][0]
            self.assertNotIn('path',source)
            record=next(m for m in opened.payload['models']['models'] if m['id']==source['model_id'])
            self.assertEqual(hashlib.sha256(opened.members[record['uri'][8:]]).hexdigest(),source['sha256'])
            identity={'project_path':str(path),'expected_manifest_payload_sha256':opened.manifest['manifest_payload_sha256']}
            study=read_assembly_field_study_in_project(identity,application_version='test')
            self.assertEqual(study['state'],'current')
            self.assertEqual(study['record']['request'],result['request'])
            from python.spike_core.assembly_thermal_components import MATERIALS_KEY
            self.assertEqual(opened.payload['assembly_ir']['extensions'][MATERIALS_KEY]['resin'],params['assignments']['materials'][1])
            setup=opened.payload['analyses']['assembly_thermal_mesh_setup']
            self.assertNotIn('encapsulation',setup)
            self.assertEqual(setup['parts']['encapsulation:fill'],'resin')
            self.assertEqual(result['retained_assignments'],setup)
            regenerated=run_assembly_thermal_mesh_in_project({**identity,'assignments':setup,'mesh_options':params['mesh_options']})
            self.assertEqual(regenerated['status'],'completed',regenerated.get('blockers'))
            self.assertEqual(len(regenerated['request']['bodies']),2)
            self.assertAlmostEqual(regenerated['evidence'][1]['metrics']['cad_volume_mm3'],expected_volume,places=8)

    def test_actual_coating_project_reopen_and_regeneration(self):
        self._assert_project_generation('coating',4.064)

    def test_actual_potting_project_reopen_and_regeneration(self):
        self._assert_project_generation('potting',44.)

    def test_invalid_paths_conflicts_and_digest_leave_project_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'study.spike';params=package_fixture(path)
            opened=read_project(path,include_members=True)
            payload=copy.deepcopy(opened.payload);payload['assembly_ir'],_=_assembly_identity(payload['assembly_ir'])
            root=Path(d)/'mesh'
            generated=run_assembly_thermal_mesh(payload,params['assignments'],params['mesh_options'],root,
                                               artifact_reader=_artifact_reader(path,opened))
            self.assertEqual(generated['status'],'completed',generated.get('blockers'))
            snapshot=path.read_bytes()
            outside=Path(d)/'outside.step';outside.write_bytes(Path(generated['encapsulation_sources'][0]['path']).read_bytes())
            for mutation in (lambda s:s.update(path=str(outside)),lambda s:s.update(model_id='original-case'),
                             lambda s:s.update(sha256='0'*64),lambda s:s.update(occurrence_id='board-a')):
                bad=copy.deepcopy(generated);mutation(bad['encapsulation_sources'][0])
                with self.assertRaises(ProjectPackageError):
                    retain_generated_encapsulation(params,opened,path,bad,root,application_version='test')
                self.assertEqual(path.read_bytes(),snapshot)
            stale={**params,'expected_manifest_payload_sha256':'0'*64}
            with self.assertRaises(ProjectPackageError):
                retain_generated_encapsulation(stale,opened,path,generated,root,application_version='test')
            self.assertEqual(path.read_bytes(),snapshot)

if __name__=='__main__':unittest.main()
