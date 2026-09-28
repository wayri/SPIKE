# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest
import numpy as np
from scripts.admit_cambridge_measured_si import admit_blob,partial_crosstalk,FILES
from python.spike_core.sparameters import NetworkData


class CambridgeAdmissionTests(unittest.TestCase):
    def test_reject_unknown_and_tampered(self):
        with self.assertRaises(ValueError): admit_blob('invented.s2p',b'')
        for name,(_,_,size,_) in FILES.items():
            with self.assertRaises(ValueError): admit_blob(name,b'0'*size)

    def test_mapping_is_not_full_network(self):
        # Synthetic unit fixture only, not presented as measured evidence.
        s=np.zeros((2,2,2),dtype=complex); s[:,1,0]=[.1,.2j]
        network=NetworkData(np.array([1e6,2e6]),s,np.array([50.,50.]))
        report=partial_crosstalk(network)
        self.assertFalse(report['complete_four_port_network'])
        self.assertEqual(report['next']['trace'],[])
        self.assertAlmostEqual(report['fext']['trace'][0]['transfer_db'],-20)
        self.assertIn('1→4',report['mapping']['fext'])
        self.assertEqual(FILES['Two_Wire_S41.S2P'][3],(1,4))


if __name__=='__main__': unittest.main()
