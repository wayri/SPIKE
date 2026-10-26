# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_load_table import CfdLoadTable, CONTRACT


def table():
    return dict(contract=CONTRACT,geometry_sha256='a'*64,physics_sha256='b'*64,evidence={'scope':'analytic test anchors, not CFD validation'},
                anchors=[dict(omega_rad_s=w,torque_nm=1e-5*w*w,thrust_n=.001*w*w,case_sha256=str(i)*64)
                         for i,w in enumerate((0.,100.,200.))])


class CfdLoadTableTests(unittest.TestCase):
    def test_anchors_passivity_work_identity_and_no_mutation(self):
        t=table();saved=copy.deepcopy(t);p=CfdLoadTable(t)
        for w in (0.,50.,100.,150.,200.):
            out=p(w);self.assertGreaterEqual(out['torque_nm'],0.)
            self.assertEqual(out['power_w'],w*out['torque_nm']);self.assertFalse(out['is_blade_resolved_cfd'])
        self.assertEqual(p(100.)['torque_nm'],.1);self.assertEqual(t,saved)
        t['anchors'][1]['torque_nm']=99.;self.assertEqual(p(100.)['torque_nm'],.1)
    def test_no_extrapolation_or_forged_duplicate_identity(self):
        p=CfdLoadTable(table())
        for w in (-1.,201.,float('nan'),True):
            with self.assertRaises(ValueError):p(w)
        t=table();t['anchors'][1]['case_sha256']=t['anchors'][0]['case_sha256']
        with self.assertRaises(ValueError):CfdLoadTable(t)


if __name__=='__main__':unittest.main()
