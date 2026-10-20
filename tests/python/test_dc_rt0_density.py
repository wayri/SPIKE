# SPDX-License-Identifier: Apache-2.0
"""Independent physical-field, quantile, contact-work and ownership oracles."""
import math
import random
from fractions import Fraction
import unittest

import numpy as np
from shapely.geometry import Polygon, box

from python.spike_core.contracts import AnalysisSpec
from python.spike_core.dc_copper_domain import explicit_terminal_contacts
from python.spike_core.dc_rt0_density import (
    _percentile, reconstruct_rt0_density, rt0_dissipation_w, volume_percentile_enclosure,
)
from python.spike_core.dc_triangle_partition import partition_polygon_groups
from python.spike_core.peec_conforming_dc import (
    assemble_conforming_dc, solve_hybridized_conforming_dc, triangle_resistance,
)


def groups(shape, thickness=1., conductivity=1000.):
    return {("F.Cu","N"):{"geometry":shape,"thickness_mm":thickness,
            "conductivity_s_m":conductivity,"z_mm":0.}}


def contacts():
    return [{"id":"source","layer":"F.Cu","net":"N","geometry":box(0,0,.5,1)},
            {"id":"load","layer":"F.Cu","net":"N","geometry":box(1.5,0,2,1)}]


class DensityTests(unittest.TestCase):
    def test_finite_high_conductivity_does_not_report_false_zero_loss(self):
        # Unit uniform J=(1,0) A/mm2 over 1/2 mm3: P=500/sigma W.
        triangle = [[[0.,0.],[1.,0.],[0.,1.]]]
        loss = rt0_dissipation_w(triangle,[[1.,-1.,0.]],1.,1e308)[0]
        self.assertGreater(loss,0.)
        self.assertLess(abs(loss/5e-306-1),1e-14)
        self.assertEqual(rt0_dissipation_w(triangle,[[0.,0.,0.]],1.,1e308)[0],0.)
        with self.assertRaisesRegex(ValueError,"underflowed"):
            rt0_dissipation_w(triangle,[[1e-200,-1e-200,0.]],1.,1000.)

    def test_quantile_rank_matches_independent_exact_rational_oracle(self):
        randomizer = random.Random(20261019)
        for _ in range(100):
            count = randomizer.randint(2,24)
            values = np.array([float(randomizer.randrange(5)) for _ in range(count)])
            weights = np.array([math.ldexp(randomizer.uniform(.5,1.),randomizer.randint(-200,200))
                                for _ in range(count)])
            quantile = randomizer.choice((.01,.5,.95,.99,np.nextafter(.5,1.)))
            exact_weights = [Fraction.from_float(float(w)) for w in weights]
            threshold = Fraction.from_float(float(quantile))*sum(exact_weights,Fraction())
            prefix = Fraction()
            for index in sorted(range(count),key=lambda i:values[i]):
                prefix += exact_weights[index]
                if prefix >= threshold:
                    expected = values[index]
                    break
            self.assertEqual(_percentile(values,weights,quantile),expected)

    def test_volume_rounding_cannot_collapse_a_finite_quantile_jump(self):
        vectors = np.array([[[0.,0.]]*3,[[1.,0.]]*3])
        cases = (([19.,1.+5*np.finfo(float).eps],.95),
                 ([1.,np.nextafter(1.,2.)],.5))
        for weights,quantile in cases:
            with self.subTest(weights=weights,quantile=quantile):
                threshold = Fraction.from_float(quantile)*sum(
                    (Fraction.from_float(float(w)) for w in weights),Fraction())
                self.assertGreater(threshold,Fraction.from_float(weights[0]))
                for ordering in ((0,1),(1,0)):
                    result = volume_percentile_enclosure(
                        vectors[list(ordering)],np.array(weights)[list(ordering)],quantile)
                    self.assertEqual(result["lower_a_mm2"],1.)
                    self.assertEqual(result["upper_a_mm2"],1.)

    def test_signed_affine_45_degree_sheet_rotation_and_large_origin(self):
        base = np.array([[0.,0.],[2.,0.],[.3,1.2]])
        for angle in (0.,math.pi/4,1.17):
            rotation = np.array([[math.cos(angle),-math.sin(angle)],
                                 [math.sin(angle),math.cos(angle)]])
            triangle = base@rotation.T + [1e5,-3e5]
            density = rotation@np.array([3.,4.])
            tangent = np.roll(triangle,-2,axis=0)-np.roll(triangle,-1,axis=0)
            normals = np.column_stack((tangent[:,1],-tangent[:,0]))
            flux = .035*(normals@density)
            vectors = reconstruct_rt0_density([triangle],[flux],.035)
            np.testing.assert_allclose(vectors,np.tile(density,(1,3,1)),rtol=2e-14,atol=1e-13)
            u,v = triangle[1]-triangle[0],triangle[2]-triangle[0]
            area = abs(u[0]*v[1]-u[1]*v[0])/2
            result = volume_percentile_enclosure(vectors,[area*.035])
            self.assertAlmostEqual(result["lower_a_mm2"],5.,places=12)
            self.assertAlmostEqual(result["upper_a_mm2"],5.,places=12)
            loss = rt0_dissipation_w([triangle],[flux],.035,5.8e7)[0]
            self.assertAlmostEqual(loss,25.*area*.035*1000/5.8e7,places=15)
            matrix = triangle_resistance(triangle,5.8e7*.035*1e-3)
            self.assertAlmostEqual(loss,flux@matrix@flux,places=15)

    def test_variable_field_quantile_is_enclosed_not_centroid_substitution(self):
        # J=(x,y), unit right triangle. For radius<1/sqrt(2), disk intersection
        # is precisely a quadrant; p25 radius=sqrt(1/(2*pi)).
        values = np.array([[[0.,0.],[1.,0.],[0.,1.]]])
        expected = math.sqrt(1/(2*math.pi))
        result = volume_percentile_enclosure(values,[.5],.25,relative_tolerance=1e-4)
        self.assertLessEqual(result["lower_a_mm2"],expected)
        self.assertGreaterEqual(result["upper_a_mm2"],expected)
        self.assertLess(result["enclosure_width_a_mm2"],expected*1.1e-4)

    def test_zero_current_domains_are_not_dropped(self):
        values = np.array([[[3.,4.]]*3,[[0.,0.]]*3])
        result = volume_percentile_enclosure(values,[1.,99.])
        self.assertEqual(result["upper_a_mm2"],0.)
        self.assertEqual(result["physical_volume_mm3"],100.)

    def test_angular_annulus_unique_volume_p95_and_energy_refinement(self):
        # Independent exact field K=C*e_theta/r, C=I/(2*log(b/a)), t=1.
        # Integrated outward chord flux is -C*log(rb/ra). No implementation
        # mass/basis formula defines this oracle.
        a,b = .5,1.
        coefficient = 1/(2*math.log(b/a))
        exact_p95 = coefficient/math.sqrt(.05*b*b+.95*a*a)
        exact_energy = 2*math.pi*coefficient**2*math.log(b/a)
        errors = []
        for radial,angular in ((8,64),(16,128),(32,256)):
            triangles = []
            radii = np.linspace(a,b,radial+1)
            for r0,r1 in zip(radii,radii[1:]):
                for i in range(angular):
                    p,q = 2*math.pi*i/angular,2*math.pi*(i+1)/angular
                    v = np.array([[r0*math.cos(p),r0*math.sin(p)],
                                  [r1*math.cos(p),r1*math.sin(p)],
                                  [r1*math.cos(q),r1*math.sin(q)],
                                  [r0*math.cos(q),r0*math.sin(q)]])
                    triangles.extend((v[[0,1,2]],v[[0,2,3]]))
            triangles = np.asarray(triangles)
            start = np.roll(triangles,-1,axis=1)
            end = np.roll(triangles,-2,axis=1)
            flux = -coefficient*np.log(np.linalg.norm(end,axis=2)/np.linalg.norm(start,axis=2))
            vectors = reconstruct_rt0_density(triangles,flux,1.)
            u,v = triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]
            area = (u[:,0]*v[:,1]-u[:,1]*v[:,0])/2
            result = volume_percentile_enclosure(vectors,area)
            errors.append(abs(result["upper_a_mm2"]/exact_p95-1))
            np.testing.assert_allclose(flux.sum(axis=1),0,atol=1e-15)
            energy = float(rt0_dissipation_w(triangles,flux,1.,1000.).sum())
            self.assertLess(abs(energy/exact_energy-1),.004)
            self.assertAlmostEqual(area.sum(),angular/2*math.sin(2*math.pi/angular)*(b*b-a*a),places=12)
        self.assertLess(errors[-1],.01)
        self.assertLess(errors[-1],errors[0])

    def test_complete_polygon_contacts_preserve_work_and_inactive_volume(self):
        shape = box(0,0,2,1).union(box(3,0,4,1))
        mesh = partition_polygon_groups(groups(shape),contacts(),target_mm=.125)
        report = solve_hybridized_conforming_dc(mesh,0,1,include_density=True)
        self.assertLess(abs(report["resistance_ohm"]-(2-4*.5/3)),.002)
        self.assertLess(report["relative_energy_error"],1e-10)
        self.assertLess(report["maximum_face_kcl_error_a"],1e-10)
        field = report["current_density_observable"]
        self.assertAlmostEqual(field["physical_planar_volume_mm3"],3.)
        self.assertAlmostEqual(field["undriven_planar_volume_mm3"],1.)
        self.assertAlmostEqual(field["planar_dissipation_w"],report["resistance_ohm"],places=11)
        self.assertFalse(field["complete_physical_volume"])
        self.assertTrue(field["complete_planar_polygon_partition"])

    def test_holed_polygon_ownership_and_contact_admission(self):
        shape = Polygon([(0,0),(2,0),(2,2),(0,2)],holes=[[(.8,.8),(.8,1.2),(1.2,1.2),(1.2,.8)]])
        mesh = partition_polygon_groups(groups(shape),[],target_mm=.25)
        report = mesh.branch_admission["conforming_partition"]["groups"][0]
        self.assertLess(report["omitted_area_mm2"],1e-12)
        self.assertLess(report["outside_area_mm2"],1e-12)
        self.assertAlmostEqual(report["represented_area_mm2"],3.84)
        system = assemble_conforming_dc(mesh)
        self.assertAlmostEqual(system.areas_mm2.sum(),3.84)
        with self.assertRaisesRegex(ValueError,"leaves actual copper"):
            partition_polygon_groups(groups(shape),[{"id":"hole","layer":"F.Cu","net":"N",
                "geometry":box(.9,.9,1.1,1.1)}],target_mm=.25)
        with self.assertRaisesRegex(ValueError,"overlapping|Overlapping"):
            partition_polygon_groups(groups(box(0,0,2,1)),[contacts()[0],dict(contacts()[0],id="other")],target_mm=.25)

    def test_position_only_request_is_not_given_an_invented_contact(self):
        spec = AnalysisSpec(mode="dc",net_names=["N"],
            sources=[{"id":"original","position_mm":[1,2],"layer":"F.Cu"}])
        with self.assertRaisesRegex(ValueError,"physical contact footprint is unspecified"):
            explicit_terminal_contacts(spec)
        self.assertNotIn("contact_polygon_mm",spec.sources[0])

    def test_malformed_overflow_underflow_and_budget_fail_closed(self):
        triangle = np.array([[[0.,0.],[1.,0.],[0.,1.]]])
        for changed in (triangle[:,[0,2,1]],triangle*1e200,triangle*1e-200):
            with self.assertRaises(ValueError):
                reconstruct_rt0_density(changed,[[1.,-1.,0.]],1.)
        with self.assertRaises(ValueError):
            reconstruct_rt0_density(triangle,[[1e308,1e308,1e308]],1.)
        with self.assertRaises(ValueError):
            rt0_dissipation_w(triangle,[[1e200,-1e200,0.]],1.,1000.)
        with self.assertRaisesRegex(ValueError,"sum overflowed"):
            volume_percentile_enclosure(np.zeros((2,3,2)),[1e308,1e308])
        with self.assertRaisesRegex(ValueError,"budget exhausted"):
            volume_percentile_enclosure(triangle,[1.],max_subcells=1)
        with self.assertRaisesRegex(ValueError,"budget"):
            partition_polygon_groups(groups(box(0,0,2,1)),contacts(),target_mm=.001,max_triangles=10)


if __name__ == "__main__":
    unittest.main()
