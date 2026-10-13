# SPDX-License-Identifier: Apache-2.0
"""Independent analytical priority-volume and bounded tetrahedral oracles."""
import unittest

from python.spike_core.assembly_em_board_geometry import prepare_routed_board_volume
from python.spike_core.assembly_em_planar_mesher import mesh_material_prisms, partition_material_prisms
from tests.python.test_assembly_em_board_geometry import fixture


class PlanarMaterialMeshTests(unittest.TestCase):
    def test_exact_rectangular_priority_volumes(self):
        source,stack=fixture();source['drills']=[]
        job=prepare_routed_board_volume(source,stack)['job']
        result=mesh_material_prisms(job)
        volumes=result['evidence']['tetrahedral_material_volume_mm3']
        copper=(4+1+16)*.035
        self.assertAlmostEqual(volumes['copper'],copper,places=11)
        self.assertAlmostEqual(volumes['fr4'],96-copper,places=11)
        self.assertFalse(result['evidence']['globally_conforming_fem'])
        self.assertEqual(result['evidence']['source_solids'],4)
        self.assertTrue(result['boundary_faces'])

    def test_drill_voids_and_barrel_materials_retained(self):
        source,stack=fixture();job=prepare_routed_board_volume(source,stack)['job']
        result=mesh_material_prisms(job)
        volumes=result['evidence']['tetrahedral_material_volume_mm3']
        self.assertEqual(set(volumes),{'copper','fr4','air'})
        self.assertAlmostEqual(sum(volumes.values()),96,places=9)
        self.assertAlmostEqual(volumes['air'],3.141592653589793*.15**2*1.6,delta=.002)
        self.assertEqual(result['evidence']['predicted_cells'],result['mesh']['counts']['cells'])
        self.assertEqual(set(result['material_map']),set(volumes))

    def test_resource_failure_precedes_tetra_allocation(self):
        source,stack=fixture();job=prepare_routed_board_volume(source,stack)['job']
        with self.assertRaisesRegex(ValueError,'complete geometry needs'):
            mesh_material_prisms(job,max_cells=4)

    def test_equal_priority_different_materials_rejected(self):
        source,stack=fixture();source['drills']=[]
        job=prepare_routed_board_volume(source,stack)['job']
        duplicate={**job['solids'][1],'id':'conflict','material_id':'other'}
        job['solids'].append(duplicate);job['object_metadata']['conflict']={'kind':'test'}
        with self.assertRaisesRegex(ValueError,'equal-priority'):
            partition_material_prisms(job)

    def test_precision_topology_loss_rejected(self):
        source,stack=fixture();job=prepare_routed_board_volume(source,stack)['job']
        job['solids'][1]['shape']['holes_mm']=[[[2,1.2],[2.0000001,1.2],[2.0000001,1.3],[2,1.3]]]
        with self.assertRaisesRegex(ValueError,'source topology'):
            partition_material_prisms(job)


if __name__=='__main__':unittest.main()
