# SPDX-License-Identifier: Apache-2.0
"""Independent hover momentum, manufactured inflow, energy and rejection tests."""
import copy
import math
import unittest

from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_propeller import CONTRACT, evaluate_propeller


def nominal(cells=32):
    return {'contract':CONTRACT, 'blade_count':2,
        'radial_stations_m':[.03,.15], 'chord_m':[.018,.012], 'twist_rad':[.18,.12],
        'density_kg_m3':1.225, 'dynamic_viscosity_pa_s':1.81e-5, 'speed_of_sound_m_s':343.,
        'polar':{'lift_slope_per_rad':6., 'drag_coefficient':.012,
            'alpha_valid_rad':[0.,.2], 'reynolds_valid':[0.,2e6],
            'source':'Illustrative assumed attached linear polar; no measured airfoil qualification'},
        'radial_cells':cells, 'relative_tolerance':1e-10, 'max_iterations':80}


class HoverPropellerTests(unittest.TestCase):
    def test_exact_zero_and_negative_rotation(self):
        result = evaluate_propeller(nominal(), 0.)
        for key in ('torque_nm','thrust_n','power_w','induced_power_w','profile_drag_power_w'):
            self.assertEqual(result[key], 0.)
        self.assertTrue(all(row['disk_axial_velocity_m_s']==0 and row['thrust_n']==0
                            for row in result['radial_airflow']))
        with self.assertRaisesRegex(ValueError, 'Negative rotation'):
            evaluate_propeller(nominal(), -.01)

    def test_manufactured_uniform_inflow_matches_analytic_actuator_disk(self):
        # Construct a blade from an independent desired uniform disk velocity.
        # Input stations include integration midpoints; no interpolation error there.
        s = nominal(); cells=s['radial_cells']; root, tip=.03,.15; omega, vi=300.,1.5
        radii=[root]+[root+(i+.5)*(tip-root)/cells for i in range(cells)]+[tip]
        alpha=.08; slope=6.; blades=s['blade_count']
        chords=[]; twists=[]
        for r in radii:
            phi=math.atan2(vi,omega*r); W2=(omega*r)**2+vi**2
            chord=(4*math.pi*r*vi**2)/(.5*blades*W2*(slope*alpha)*math.cos(phi))
            chords.append(chord);twists.append(phi+alpha)
        s.update(radial_stations_m=radii,chord_m=chords,twist_rad=twists)
        s['polar'].update(drag_coefficient=0.,alpha_valid_rad=[0.,.3])
        result=evaluate_propeller(s,omega)
        area=math.pi*(tip**2-root**2); expected=2*s['density_kg_m3']*area*vi**2
        self.assertAlmostEqual(result['thrust_n']/expected,1.,delta=2e-10)
        self.assertAlmostEqual(result['power_w']/(expected*vi),1.,delta=2e-10)
        self.assertEqual(result['profile_drag_power_w'],0.)
        self.assertAlmostEqual(result['induced_power_w']/result['ideal_uniform_active_disk_power_w'],1.,delta=2e-10)
        for row in result['radial_airflow']:
            self.assertAlmostEqual(row['disk_axial_velocity_m_s'],vi,delta=2e-9)
            self.assertAlmostEqual(row['far_wake_axial_velocity_m_s'],2*vi,delta=4e-9)
            self.assertAlmostEqual(row['alpha_rad'],alpha,delta=2e-10)

    def test_local_mass_momentum_and_energy_closure(self):
        s=nominal(); r=evaluate_propeller(s,500.)
        self.assertGreater(r['thrust_n'],0); self.assertGreater(r['torque_nm'],0)
        self.assertAlmostEqual(r['power_w'],500*r['torque_nm'],places=13)
        self.assertAlmostEqual(r['power_w'],r['induced_power_w']+r['profile_drag_power_w'],places=12)
        self.assertGreaterEqual(r['induced_power_w'],r['ideal_uniform_active_disk_power_w']*(1-1e-9))
        for row in r['radial_airflow']:
            area=row['disk_area_m2'];v=row['disk_axial_velocity_m_s'];rho=s['density_kg_m3']
            thrust=2*rho*area*v*v
            self.assertAlmostEqual(row['thrust_n']/thrust,1.,delta=2e-10)
            self.assertAlmostEqual(row['mass_flow_kg_s'],rho*v*area,places=14)
            self.assertAlmostEqual(row['far_wake_kinetic_power_w']/row['induced_power_w'],1.,delta=2e-10)
            self.assertAlmostEqual(500*row['torque_nm'],row['induced_power_w']+row['profile_drag_power_w'],places=13)
        self.assertFalse(r['validity']['resolved_cfd'])
        self.assertFalse(r['validity']['angular_momentum_wake_verified'])
        self.assertFalse(r['production_qualified'])

    def test_geometry_density_and_speed_are_actual_inputs(self):
        s=nominal();a=evaluate_propeller(s,200.);b=evaluate_propeller(s,400.)
        for key in ['thrust_n','torque_nm']:
            self.assertAlmostEqual(b[key]/a[key],4.,places=12)
        self.assertAlmostEqual(b['power_w']/a['power_w'],8.,places=12)
        s['density_kg_m3']*=2;c=evaluate_propeller(s,200.)
        for key in ['thrust_n','torque_nm','power_w']:
            self.assertAlmostEqual(c[key]/a[key],2.,places=12)
        s=nominal();s['chord_m']=[x*1.2 for x in s['chord_m']]
        changed=evaluate_propeller(s,200.)
        self.assertGreater(changed['thrust_n'],a['thrust_n']*1.05)
        s=nominal();s['radial_stations_m']=[x*2 for x in s['radial_stations_m']];s['chord_m']=[x*2 for x in s['chord_m']]
        bigger=evaluate_propeller(s,200.)
        self.assertAlmostEqual(bigger['thrust_n']/a['thrust_n'],16.,places=10)
        self.assertAlmostEqual(bigger['torque_nm']/a['torque_nm'],32.,places=10)

    def test_positive_profile_drag_and_radial_quadrature_refinement(self):
        s=nominal();zero=copy.deepcopy(s);zero['polar']['drag_coefficient']=0.
        self.assertGreater(evaluate_propeller(s,500.)['profile_drag_power_w'],0.)
        self.assertEqual(evaluate_propeller(zero,500.)['profile_drag_power_w'],0.)
        levels=[evaluate_propeller(nominal(n),500.) for n in (16,32,64,128)]
        for key in ['thrust_n','torque_nm']:
            differences=[abs(b[key]-a[key]) for a,b in zip(levels,levels[1:])]
            self.assertGreater(differences[0]/differences[1],3.8)
            self.assertGreater(differences[1]/differences[2],3.8)
        self.assertLess(abs(levels[-1]['thrust_n']-levels[-2]['thrust_n'])/levels[-1]['thrust_n'],1e-5)

    def test_invalid_geometry_and_unsupported_physics_fail(self):
        requests=[]
        s=nominal();s['radial_stations_m']=[.15,.03];requests.append(s)
        s=nominal();s['twist_rad']=[.4,.12];requests.append(s)
        s=nominal();s['chord_m']=[1.,1.];requests.append(s)
        s=nominal();s['polar']['drag_coefficient']=-.01;requests.append(s)
        s=nominal();s['density_kg_m3']=float('nan');requests.append(s)
        s=nominal();s['polar']['alpha_valid_rad']=[.01,.2];requests.append(s)
        s=nominal();s['axial_advance_m_s']=1.;requests.append(s)
        s=nominal();s['blade_count']=True;requests.append(s)
        s=nominal();s['chord_m']=[.018];requests.append(s)
        for request in requests:
            with self.subTest(request=request):
                with self.assertRaises(ValueError):evaluate_propeller(request,300.)
        for speed in [float('nan'),float('inf'),True,10000.,1e-200]:
            with self.subTest(speed=speed):
                with self.assertRaises(ValueError):evaluate_propeller(nominal(),speed)
        s=nominal();s['polar']['reynolds_valid']=[1e6,2e6]
        with self.assertRaisesRegex(ValueError,'Reynolds'):evaluate_propeller(s,100.)
        self.assertEqual(evaluate_propeller(s,0.)['power_w'],0.)

    def test_failed_root_and_mutable_result_isolation(self):
        s=nominal();s['max_iterations']=1
        with self.assertRaisesRegex(ValueError,'failed to converge'):evaluate_propeller(s,300.)
        s=nominal();a=evaluate_propeller(s,300.);a['radial_airflow'][0]['thrust_n']=1e99
        b=evaluate_propeller(s,300.)
        self.assertLess(b['radial_airflow'][0]['thrust_n'],1.)
        s['twist_rad'][0]*=.9
        self.assertNotEqual(b['spec_sha256'],evaluate_propeller(s,300.)['spec_sha256'])


if __name__=='__main__':unittest.main()
