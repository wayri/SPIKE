# SPDX-License-Identifier: Apache-2.0
"""Independent cross-ratio and simultaneous-wave SI08-S07 oracles."""
from copy import deepcopy
import unittest

import numpy as np

from python.spike_core.solvers.signal_integrity.networks import multiport_calibration as subject


def ri(z):
    return {"real": float(z.real), "imag": float(z.imag)}


def read_ri(z):
    return complex(z["real"], z["imag"])


def encode(a):
    a = np.asarray(a)
    return ri(complex(a)) if a.ndim == 0 else [encode(row) for row in a]


def decode(a):
    return read_ri(a) if isinstance(a, dict) else np.array([decode(row) for row in a])


def basis(n, count):
    labels = []
    for k in range(count):
        for kind in ("reflection", "measured"):
            labels += [f"f{k}.reflection_standards{j}.{kind}.p{i}.{part}"
                       for j in range(3) for i in range(n) for part in ("real", "imag")]
        for field in ("coupling_standard.s_parameters", "coupling_standard.measured", "dut.measured"):
            labels += [f"f{k}.{field}.p{i}.p{j}.{part}"
                       for i in range(n) for j in range(n) for part in ("real", "imag")]
    return labels


def forward(s, d, u, v, w):
    """Solve coupled incident/reflected waves, without a reduced inverse."""
    n = len(d)
    block = np.block([[np.eye(n), -np.diag(v)], [-s, np.eye(n)]])
    waves = np.linalg.solve(block, np.vstack((np.diag(w), np.zeros((n, n)))))
    return np.diag(d) + np.diag(u) @ waves[n:]


def fixture(n=3, count=2, gauge=1+0j):
    known, measured, coupling, coupling_measured, dut_measured, expected, terms = [], [], [], [], [], [], []
    for k in range(count):
        p = np.arange(n)
        d = .025 + .009*p + 1j*(.018-.004*p+.006*k)
        u = gauge*(.83+.075*p+1j*(.11-.032*p+.017*k))
        v = -.12+.018*p+1j*(.055+.007*p-.009*k)
        w = (.91-.027*p+1j*(-.06+.013*p-.021*k))/gauge
        g = np.array([.94+1j*(.03+.008*p), -.91+1j*(.025-.007*p), .02+.007*p+1j*.015])
        m = np.array([d+u*w*row/(1-v*row) for row in g])
        i, j = np.indices((n, n))
        c = .17+.035*i+.026*j+1j*(.04-.014*i+.019*j+.005*k)
        c[np.diag_indices(n)] = -.08+.017*p+1j*(.025+.009*p)
        s = .11+.06*i-.023*j+1j*(.03+.021*i+.032*j+.014*k)
        s[np.diag_indices(n)] = .22-.03*p+1j*(.12+.014*p)
        s[n-1, 0] = 1.24+.19j+.03*k
        known.append(g); measured.append(m); coupling.append(c)
        coupling_measured.append(forward(c,d,u,v,w)); dut_measured.append(forward(s,d,u,v,w))
        expected.append(s); terms.append((d,u*w,v,u/u[0],w*u[0]))
    dim = 2*count*(6*n+3*n*n)
    request = {"contract": "spike/multiport-calibration-request/v1", "id": "independent-wave-case",
               "port_names": [f"plane.{p}" for p in range(n)], "reference_impedance_ohm": 50.,
               "frequencies_hz": [73e6*(k+1)**2 for k in range(count)],
               "measurement_basis": "coherent_wave_matrix_ratio", "gain_reference_port": "plane.0",
               "reflection_standards": [
                   {"id": f"standard-{j}", "provenance": "Original synthetic supplied reflection standard",
                    "reflection": encode(np.array(known)[:,j]), "measured": encode(np.array(measured)[:,j])}
                   for j in range(3)],
               "coupling_standard": {"id": "known-coupler", "provenance": "Original dense known synthetic coupling matrix",
                                     "s_parameters": encode(coupling), "measured": encode(coupling_measured)},
               "dut": {"id": "active-nonreciprocal", "provenance": "Original simultaneous wave-equation synthesis",
                       "measured": encode(dut_measured)},
               "covariance": {"basis": basis(n,count), "matrix": np.zeros((dim,dim)).tolist(),
                              "provenance": "Explicit original synthetic real joint covariance"}}
    return request, np.array(expected), terms


def coordinates(req):
    """Yield actual RI dicts in independently authored contract order."""
    for k in range(len(req["frequencies_hz"])):
        for kind in ("reflection", "measured"):
            for standard in req["reflection_standards"]:
                yield from standard[kind][k]
        for record, field in (("coupling_standard", "s_parameters"), ("coupling_standard", "measured"), ("dut", "measured")):
            for row in req[record][field][k]:
                yield from row


def vector(req):
    return np.array([value[part] for value in coordinates(req) for part in ("real", "imag")])


def replace_vector(req, x):
    changed = deepcopy(req)
    for target, pair in zip(coordinates(changed), np.asarray(x).reshape(-1,2)):
        target.update(real=float(pair[0]), imag=float(pair[1]))
    return changed


def real_vector(z):
    z = np.asarray(z).ravel()
    return np.column_stack((z.real,z.imag)).ravel()


def cross_ratio_terms(g, m):
    """Expand the three-point cross ratio; no scalar fitting-system solve."""
    g0,g1,g2 = g
    m0,m1,m2 = m
    a = (g1-g0)*(m1-m2)
    b = (g1-g2)*(m1-m0)
    h0 = -a*g2+b*g0
    n0 = -a*g2*m0+b*g0*m2
    n1 = a*m0-b*m2
    d = n0/h0
    v = -(a-b)/h0
    return d, n1/h0+d*v, v


def oracle(x, n, count, reference=0):
    results = []
    for row in np.asarray(x).reshape(count,-1):
        z = row[::2]+1j*row[1::2]
        g,m = z[:3*n].reshape(3,n),z[3*n:6*n].reshape(3,n)
        c,mc,md = z[6*n:].reshape(3,n,n)
        d,t,v = cross_ratio_terms(g,m)
        provisional = forward(c, np.zeros(n), np.ones(n), v, t)
        u = np.ones(n,dtype=complex)
        for i in range(n):
            if i != reference:
                u[i] = mc[i,reference]/provisional[i,reference]
        w = t/u
        # Reconstruct internal waves from measured responses, then solve S*a=b.
        reflected = (md-np.diag(d))/u[:,None]
        incident = np.diag(w)+v[:,None]*reflected
        results.append(np.linalg.solve(incident.T, reflected.T).T)
    return real_vector(results)


def finite_jacobian(x, n, count, reference=0):
    step = 2e-6
    return np.column_stack([(oracle(x+shift,n,count,reference)-oracle(x-shift,n,count,reference))/(2*step)
                            for shift in step*np.eye(len(x))])


def dense_factor(n):
    i,j = np.indices((n,n))
    return np.diag(.4+np.arange(n)/n)+.08*np.cos((i+1)*(j+2))+.06*np.sin(i+2*j)


def output(result):
    return decode(result["derived_network"]["s_parameters"])


class IndependentMultiportCalibrationTests(unittest.TestCase):
    def test_two_three_four_port_truth_and_independent_waves(self):
        for n in (2,3,4):
            for count in (1,2):
                with self.subTest(n=n,count=count):
                    req,expected,terms = fixture(n,count)
                    result = subject.calibrate_multiport(req)
                    np.testing.assert_allclose(output(result),expected,rtol=2e-11,atol=2e-11)
                    np.testing.assert_allclose(real_vector(output(result)),oracle(vector(req),n,count),rtol=2e-11,atol=2e-11)
                    for got,wanted in zip(result["coefficients"],terms):
                        for key,value in zip(("directivity","reflection_tracking","source_match","outward_gain","inward_gain"),wanted):
                            np.testing.assert_allclose(decode(got[key]),value,rtol=2e-11,atol=2e-11)
                    self.assertGreater(abs(output(result)[0,-1,0]),1.)
                    self.assertGreater(np.linalg.norm(output(result)[0]-output(result)[0].T),.5)
                    self.assertEqual(subject.input_basis(req["port_names"],count),basis(n,count))

    def test_all_coordinates_and_dense_joint_covariance(self):
        for n in (2,3,4):
            with self.subTest(n=n):
                req,_,_ = fixture(n,2)
                x = vector(req)
                factor = 1e-4*dense_factor(len(x)); cov = factor@factor.T
                req["covariance"]["matrix"] = cov.tolist()
                result = subject.calibrate_multiport(req)
                jac = finite_jacobian(x,n,2)
                np.testing.assert_allclose(result["sensitivity"],jac,rtol=3e-6,atol=3e-8)
                wanted = jac@cov@jac.T
                np.testing.assert_allclose(result["covariance"],wanted,rtol=5e-6,atol=2e-14)
                self.assertGreater(np.linalg.norm(wanted[:2*n*n,2*n*n:]),1e-10)
                self.assertGreater(np.linalg.norm(wanted-jac@np.diag(np.diag(cov))@jac.T),1e-9)
                self.assertEqual(np.count_nonzero(np.asarray(result["sensitivity"])[:2*n*n,len(x)//2:]),0)

    def test_gauge_scaling_and_reference_changes(self):
        req,expected,_ = fixture(4,2)
        for gauge in (1+0j,-.7+1.1j,2.3-.6j):
            changed,_,_ = fixture(4,2,gauge)
            np.testing.assert_allclose(vector(changed),vector(req),rtol=2e-11,atol=2e-11)
            for ref in (0,2,3):
                changed["gain_reference_port"] = changed["port_names"][ref]
                result = subject.calibrate_multiport(changed)
                np.testing.assert_allclose(output(result),expected,rtol=2e-11,atol=2e-11)
                np.testing.assert_allclose(real_vector(output(result)),oracle(vector(changed),4,2,ref),rtol=2e-11,atol=2e-11)

    def test_port_permutation_reorders_full_covariance(self):
        req,_,_ = fixture(3,2)
        x = vector(req); factor = 1e-4*dense_factor(len(x)); cov = factor@factor.T
        req["covariance"]["matrix"] = cov.tolist()
        baseline = subject.calibrate_multiport(req)
        order = [2,0,1]
        changed = deepcopy(req)
        changed["port_names"] = [req["port_names"][i] for i in order]
        for record in changed["reflection_standards"]:
            for kind in ("reflection","measured"):
                record[kind] = encode(decode(record[kind])[:,order])
        for record,field in (("coupling_standard","s_parameters"),("coupling_standard","measured"),("dut","measured")):
            changed[record][field] = encode(decode(changed[record][field])[:,order][:,:,order])
        local = [3*j+i for j in range(6) for i in order]
        local += [18+9*b+3*i+j for b in range(3) for i in order for j in order]
        indices = [90*k+2*j+p for k in range(2) for j in local for p in (0,1)]
        changed["covariance"]["matrix"] = cov[np.ix_(indices,indices)].tolist()
        result = subject.calibrate_multiport(changed)
        outputs = [18*k+2*(3*i+j)+p for k in range(2) for i in order for j in order for p in (0,1)]
        np.testing.assert_allclose(output(result),output(baseline)[:,order][:,:,order],rtol=2e-11,atol=2e-11)
        np.testing.assert_allclose(result["covariance"],np.asarray(baseline["covariance"])[np.ix_(outputs,outputs)],rtol=5e-6,atol=2e-14)
        np.testing.assert_allclose(result["sensitivity"],np.asarray(baseline["sensitivity"])[np.ix_(outputs,indices)],rtol=3e-6,atol=3e-8)

    def test_symmetric_nonlinear_small_noise_refinement(self):
        req,_,_ = fixture(3,2)
        x = vector(req); factor = dense_factor(len(x)); errors = []
        for scale in (2e-4,1e-4,5e-5):
            req["covariance"]["matrix"] = (scale**2*(factor@factor.T)).tolist()
            linear = np.asarray(subject.calibrate_multiport(req)["covariance"])
            shifts = np.sqrt(len(x))*scale*factor.T
            points = np.array([oracle(x+sign*shift,3,2) for shift in shifts for sign in (-1,1)])
            centered = points-points.mean(axis=0)
            nonlinear = centered.T@centered/len(points)
            errors.append(np.linalg.norm(nonlinear-linear)/np.linalg.norm(linear))
        self.assertLess(errors[1],errors[0]/2.5,errors)
        self.assertLess(errors[2],errors[1]/2.5,errors)
        self.assertLess(errors[2],2e-5,errors)

    def test_zero_and_rank_one_covariance(self):
        req,_,_ = fixture(2,2)
        x = vector(req); jac = finite_jacobian(x,2,2)
        direction = 1e-4*np.cos(np.arange(len(x))*.37)
        for cov in (np.zeros((len(x),len(x))),np.outer(direction,direction)):
            req["covariance"]["matrix"] = cov.tolist()
            result = subject.calibrate_multiport(req)
            np.testing.assert_allclose(result["covariance"],jac@cov@jac.T,rtol=5e-6,atol=2e-14)

    def test_redundant_measurements_remain_diagnostic_only(self):
        req,_,_ = fixture(3,2)
        baseline = subject.calibrate_multiport(req)
        req["coupling_standard"]["measured"][1][1][2] = ri(.8+.6j)
        result = subject.calibrate_multiport(req)
        np.testing.assert_allclose(output(result),output(baseline),rtol=2e-11,atol=2e-11)
        self.assertGreater(result["diagnostics"][1]["coupling_standard_consistency_residual"],.01)
        self.assertFalse(result["model_consistency_qualified"])
        col = basis(3,2).index("f1.coupling_standard.measured.p1.p2.real")
        self.assertEqual(np.count_nonzero(np.asarray(result["sensitivity"])[:,col:col+2]),0)

    def assert_rejected_unchanged(self,req):
        before = deepcopy(req)
        with self.assertRaises(subject.MultiportCalibrationError) as caught:
            subject.calibrate_multiport(req)
        self.assertTrue(caught.exception.code)
        self.assertEqual(req,before)

    def test_missing_reference_paths_and_zero_gains(self):
        for mode in ("disconnected","zero_gain"):
            req,_,_ = fixture(3,2)
            if mode == "disconnected":
                # Diagonal C has no direct or effective path from the reference.
                req["coupling_standard"]["s_parameters"][1] = encode(.1*np.eye(3))
            else:
                req["coupling_standard"]["measured"][1][2][0] = ri(0j)
            with self.subTest(mode=mode):
                self.assert_rejected_unchanged(req)

    def test_coincident_standards_or_collapsed_tracking_at_last_frequency(self):
        for mode in ("reflection","measured"):
            req,_,_ = fixture(2,2)
            for record in req["reflection_standards"]:
                record[mode][1][1] = ri(.2+.1j)
            with self.subTest(mode=mode):
                self.assert_rejected_unchanged(req)

    def test_coupling_feedback_and_dut_inverse_poles_at_last_frequency(self):
        for mode in ("coupling","dut"):
            req,_,terms = fixture(2,2)
            d,t,v,u,w = terms[1]
            if mode == "coupling":
                req["coupling_standard"]["s_parameters"][1] = encode(np.diag(1/v))
            else:
                # X=-V^-1 makes every DUT inverse direction singular.
                req["dut"]["measured"][1] = encode(np.diag(d-t/v))
            with self.subTest(mode=mode):
                self.assert_rejected_unchanged(req)

    def test_near_poles_cannot_hide_behind_small_condition_number(self):
        for mode in ("coupling","dut"):
            req,_,terms = fixture(2,2)
            d,t,v,u,w = terms[1]
            epsilon = 1e-12
            if mode == "coupling":
                # I-CV=epsilon*H has condition 1.5 but loses twelve digits.
                h = np.array([[1.,.2],[.2,1.]])
                req["coupling_standard"]["s_parameters"][1] = encode((np.eye(2)-epsilon*h)/v[None,:])
            else:
                # I+XV=epsilon*I: relative condition alone is exactly one.
                req["dut"]["measured"][1] = encode(np.diag(d+(-1+epsilon)*t/v))
            with self.subTest(mode=mode):
                self.assert_rejected_unchanged(req)

    def test_source_snapshot_and_result_ownership(self):
        req,_,_ = fixture(2,2)
        before = deepcopy(req)
        result = subject.calibrate_multiport(req)
        result["derived_network"]["s_parameters"][0][0][0]["real"] = 9.
        result["derived_network"]["frequencies_hz"][0] = 99.
        self.assertEqual(req,before)
        self.assertEqual(result["source_request"],before)


if __name__ == "__main__":
    unittest.main()
