# SPDX-License-Identifier: Apache-2.0
"""Original quadratic energy ledger observing one actual initialized trajectory.

On each PWL interval y=[z,u,delta_u] obeys dy/dtau=G*y for tau in [0,1].
Normalize y0, B=y0*y0.T, and integrate J=integral exp(G*t) B exp(G.T*t) dt.
A small scaled block exponential [[G,B],[0,-G.T]] gives J_delta=E12 E11.T.
Covariance doubling J_2t=J_t+E_t J_t E_t.T avoids exponentiating a large
unstable -G.T block. Linear physical output rows then integrate products
as h*a.T*J*b. No symmetry repair, PSD projection or heat clipping is used.
The boundary identity is Wsource-Wnetwork-heat-(Efinal-Einitial)=0 per port;
arbitrary fitted-network work is signed and has no inferred storage meaning.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.linalg import expm

from . import sparameter_rlc_initial as initialized

rlc = initialized.rlc
REQUEST_CONTRACT = "spike/rlc-energy-ledger-request/v1"
RESULT_CONTRACT = "spike/rlc-energy-ledger-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024
_MAPS = ("source_work_j_by_port", "network_work_j_by_port", "resistor_heat_j_by_port",
         "initial_boundary_storage_j_by_port", "final_boundary_storage_j_by_port", "balance_residual_j_by_port")


class SParameterRlcEnergyError(ValueError):
    """Ledger admission or integration failure, without partial success."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_RLC_ENERGY_"+code.upper()


def _require(condition, message, code="numerical_failure"):
    if not condition:
        raise SParameterRlcEnergyError(code, message)


def _generator(context, duration):
    count, n = len(context["closed"]), len(context["ports"])
    matrix = np.zeros((count+2*n, count+2*n))
    matrix[:count, :count] = duration*context["closed"]
    matrix[:count, count:count+n] = duration*context["forcing"]
    matrix[count:count+n, count+n:] = np.eye(n)
    norm = float(np.linalg.norm(matrix, 2))
    _require(math.isfinite(norm) and norm <= 1e6, "Ledger generator exceeds supported range", "resource_limit")
    folds = max(0, int(math.ceil(math.log2(max(1., 2*norm)))))
    return matrix, folds


def _gramian(generator, vector, folds, poll):
    """Return normalized covariance integral and independent identity diagnostics."""
    norm = rlc.rational._norm
    scale = norm(vector)
    seed = vector/scale if scale else np.zeros_like(vector)
    covariance = np.outer(seed, seed)
    _require(not np.any((seed[:, None] != 0) & (seed[None, :] != 0) & (covariance == 0)), "Covariance seed underflows")
    delta = math.ldexp(1., -folds)
    small_g, small_b = delta*generator, delta*covariance
    _require(not np.any((generator != 0) & (small_g == 0)) and not np.any((covariance != 0) & (small_b == 0)), "Scaled Gramian coefficients underflow")
    m = len(vector)
    block = np.zeros((2*m, 2*m)); block[:m, :m] = small_g; block[:m, m:] = small_b; block[m:, m:] = -small_g.T
    poll()
    exponential = expm(block)
    evolution = exponential[:m, :m]
    gramian = exponential[:m, m:]@evolution.T
    _require(np.isfinite(gramian).all() and np.isfinite(evolution).all(), "Nonfinite scaled Gramian exponential")
    for _ in range(folds):
        poll()
        gramian = gramian+evolution@gramian@evolution.T
        evolution = evolution@evolution
        _require(np.isfinite(gramian).all() and np.isfinite(evolution).all(), "Nonfinite Gramian doubling")
    gnorm = norm(gramian)
    symmetry = norm(gramian-gramian.T)/gnorm if gnorm else 0.
    _require(math.isfinite(symmetry) and symmetry <= 1e-10, "Gramian symmetry residual exceeds tolerance")
    # The symmetric part is examined only; the returned Gramian is never repaired.
    eigenvalues = np.linalg.eigvalsh(.5*(gramian+gramian.T))
    _require(float(eigenvalues[0]) >= -1e-10*gnorm, "Gramian positive-semidefinite admission failed")
    left = generator@gramian+gramian@generator.T
    right = evolution@covariance@evolution.T-covariance
    denominator = 2*norm(generator)*gnorm+norm(evolution)**2*norm(covariance)+norm(covariance)
    _require(math.isfinite(denominator), "Unrepresentable Gramian residual scale")
    residual = norm(left-right)/denominator if denominator else norm(left-right)
    _require(math.isfinite(residual) and residual <= 1e-10, "Gramian integral identity residual exceeds tolerance")
    return gramian, scale, residual, symmetry


def _product_integral(a, b, gramian, duration):
    scale_a, scale_b = float(np.max(np.abs(a), initial=0)), float(np.max(np.abs(b), initial=0))
    if not scale_a or not scale_b:
        return 0.
    normalized = float((a/scale_a)@gramian@(b/scale_b))
    result = ((normalized*scale_a)*scale_b)*duration
    _require(math.isfinite(result) and (normalized == 0 or result != 0), "Quadratic integral overflows or underflows")
    return result


class _Ledger:
    def __init__(self, relative, absolute, size, poll):
        self.relative, self.absolute, self.size, self.poll = relative, absolute, size, poll
        self.intervals, self.error, self.context = [], None, None
        self.work = 0
        self.max_relative = self.max_absolute = self.max_gramian = self.max_symmetry = 0.
        self.max_folds = 0

    def _prepare(self, context):
        self.context = context
        n, count = len(context["ports"]), len(context["closed"]); m = count+2*n
        self.generators = {}
        work = context["estimated_work"]
        for left, right in zip(context["grid"], context["grid"][1:]):
            self.poll(); duration = right-left
            if duration not in self.generators:
                self.generators[duration] = _generator(context, duration)
                work += m**3
            folds = self.generators[duration][1]
            # B depends on the actual interval state, so charge every block solve.
            work += (2*m)**3+(8+4*folds)*m**3+8*n*m*m
        _require(work <= _MAX_WORK, "Aggregate trajectory/ledger work exceeds 100 million", "resource_limit")
        self.work = work
        estimate = (6*self.size+(len(context["grid"])-1)*(1024+1024*n)
                    +context["output_count"]*(1024+3072*n)+96*context["fit_frequency_count"]*n*n+524288)
        _require(estimate <= _MAX_RESULT_BYTES, "Estimated full energy ledger exceeds 16 MiB", "resource_limit")
        root = math.sqrt(context["reference"])
        incident = np.hstack((context["qmat"], context["hmat"], np.zeros((n, n))))
        outgoing = context["direct"]@incident+np.hstack((context["cmat"], np.zeros((n, 2*n))))
        voltage, current = root*(incident+outgoing), (incident-outgoing)/root
        source, supplied = np.zeros((n, m)), current.copy()
        qindices = {int(p): context["network_states"]+i for i, p in enumerate(context["inductive"])}
        vindices = {int(p): context["network_states"]+len(qindices)+i for i, p in enumerate(context["capacitive"])}
        self.qindices, self.vindices = qindices, vindices
        for port in range(n):
            r = float(context["resistance"][port])
            if port in qindices or port in vindices: factor = root
            else:
                reference = context["reference"]; scale = max(r, reference)
                c = ((reference/scale)/(r/scale+reference/scale))/root
                factor = 1/c
            source[port, count+port] = factor
            if port in qindices:
                supplied[port] = 0.; supplied[port, qindices[port]] = 1/root
            elif r > 0: supplied[port] = (source[port]-voltage[port])/r
        heat_rows = np.sqrt(context["resistance"])[:, None]*supplied
        _require(all(np.isfinite(a).all() for a in (source, supplied, voltage, current, heat_rows)), "Nonfinite physical ledger rows")
        self.rows = source, supplied, voltage, current, heat_rows

    def _storage(self, state):
        context, result = self.context, np.zeros(len(self.context["ports"]))
        root = math.sqrt(context["reference"])
        for indices, components, conversion in ((self.qindices, context["inductance"], 1/root), (self.vindices, context["capacitance"], root)):
            for port, index in indices.items():
                scaled = math.sqrt(float(components[port]))*(float(state[index])*conversion)
                energy = (scaled*scaled)/2
                _require(math.isfinite(energy) and (state[index] == 0 or energy > 0), "Boundary storage overflows or underflows")
                result[port] += energy
        return result

    def _balance(self, source, network, heat, initial, final):
        residual = source-network-heat-(final-initial)
        scale = abs(source)+abs(network)+abs(heat)+abs(initial)+abs(final)
        _require(math.isfinite(scale) and math.isfinite(residual), "Nonfinite energy balance")
        absolute = abs(residual); relative = absolute/scale if scale else 0.
        _require(absolute <= self.absolute+self.relative*scale, "Energy ledger balance exceeds supplied tolerance", "balance_failure")
        self.max_relative, self.max_absolute = max(self.max_relative, relative), max(self.max_absolute, absolute)
        return residual

    def __call__(self, context, left, right, start_state, end_state, start_input, end_input):
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                if self.context is None: self._prepare(context)
                self.poll(); duration = right-left
                generator, folds = self.generators[duration]
                vector = np.r_[start_state, start_input, end_input-start_input]
                _require(np.isfinite(vector).all(), "Unrepresentable PWL source increment")
                gramian, scale, residual, symmetry = _gramian(generator, vector, folds, self.poll)
                self.max_gramian, self.max_symmetry, self.max_folds = max(self.max_gramian, residual), max(self.max_symmetry, symmetry), max(self.max_folds, folds)
                rows = [row*scale for row in self.rows]
                _require(all(np.isfinite(row).all() for row in rows), "Unrepresentable scaled physical ledger rows")
                source_rows, supplied_rows, voltage_rows, current_rows, heat_rows = rows
                initial, final = self._storage(start_state), self._storage(end_state)
                item = {"start_time_s": left, "end_time_s": right, **{name: {} for name in _MAPS}}
                for i, port in enumerate(context["ports"]):
                    source = _product_integral(source_rows[i], supplied_rows[i], gramian, duration)
                    network = _product_integral(voltage_rows[i], current_rows[i], gramian, duration)
                    heat = _product_integral(heat_rows[i], heat_rows[i], gramian, duration)
                    _require(heat >= 0, "Negative integrated resistor heat; no clipping is permitted")
                    balance = self._balance(source, network, heat, float(initial[i]), float(final[i]))
                    for name, value in zip(_MAPS, (source, network, heat, float(initial[i]), float(final[i]), balance)):
                        item[name][port] = value
                self.intervals.append(item)
        except SParameterRlcEnergyError as error:
            self.error = error; raise
        except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
            self.error = SParameterRlcEnergyError("numerical_failure", f"Ledger integration failed: {error}")
            raise self.error from error

    def totals(self):
        totals = {name: {} for name in _MAPS}
        for port in self.context["ports"]:
            source, network, heat = [math.fsum(item[name][port] for item in self.intervals) for name in _MAPS[:3]]
            initial = self.intervals[0][_MAPS[3]][port]; final = self.intervals[-1][_MAPS[4]][port]
            balance = self._balance(source, network, heat, initial, final)
            for name, value in zip(_MAPS, (source, network, heat, initial, final, balance)): totals[name][port] = value
        return totals


def run_rlc_energy_ledger(request, *, cancel_check=None):
    """Observe one actual v2 trajectory and independently admit its energy ledger."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable", "invalid_request")
    ledger = None

    def poll():
        if cancel_check is not None:
            try: cancelled = cancel_check()
            except Exception as error: raise SParameterRlcEnergyError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "RLC energy ledger cancelled", "cancelled")

    try:
        poll(); frozen, size = rlc.prescribed._snapshot(request)
        sampling = rlc.rational.sampling
        sampling._record(frozen, {"contract", "transient_request", "relative_tolerance", "absolute_tolerance_j"}, "energy ledger request")
        _require(frozen["contract"] == REQUEST_CONTRACT, "Unsupported energy ledger contract", "invalid_request")
        relative = sampling._number(frozen["relative_tolerance"], "relative tolerance")
        absolute = sampling._number(frozen["absolute_tolerance_j"], "absolute tolerance")
        _require(0 < relative <= 1e-6 and absolute > 0, "Invalid energy balance tolerances", "invalid_request")
        ledger = _Ledger(relative, absolute, size, poll)
        trajectory = initialized._run(frozen["transient_request"], cancel_check=cancel_check, interval_observer=ledger)
        poll(); totals = ledger.totals()
        result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                  "input_digest": sampling._digest(frozen), "relative_tolerance": frozen["relative_tolerance"], "absolute_tolerance_j": frozen["absolute_tolerance_j"],
                  "transient_result": trajectory, "intervals": ledger.intervals, "totals": totals,
                  "diagnostics": {"integration_method": "scaled_covariance_gramian_doubling", "interval_count": len(ledger.intervals), "estimated_work": ledger.work,
                                  "maximum_balance_relative_residual": ledger.max_relative, "maximum_balance_absolute_residual_j": ledger.max_absolute,
                                  "maximum_gramian_relative_residual": ledger.max_gramian, "maximum_gramian_symmetry_relative_residual": ledger.max_symmetry,
                                  "maximum_doubling_count": ledger.max_folds}}
        _require(len(sampling._json(result)) <= _MAX_RESULT_BYTES, "Full energy ledger result exceeds 16 MiB", "resource_limit")
        poll(); return result
    except SParameterRlcEnergyError: raise
    except (initialized.SParameterRlcInitialError, rlc.SParameterRlcError, rlc.resistive.SParameterTerminatedError,
            rlc.prescribed.SParameterTransientError, rlc.rational.SParameterRationalError, rlc.rational.sampling.SParameterSamplingError) as error:
        if ledger is not None and ledger.error is not None: raise ledger.error from error
        raise SParameterRlcEnergyError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterRlcEnergyError("numerical_failure", f"Energy ledger failed: {error}") from error
