# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SPIKE contributors
"""Prepared, conservative one-step coupling to retained P1 tetrahedral solids.

For a device with cell fractions a_c, deposition is E*a_c/4 at each of
the cell's four vertices. Sampling uses the transpose of that same map.
The consistent heat-capacity matrix and backward-Euler step are owned by
assembly_tetra_transient. This adapter does not validate physical materials,
mesh resolution, or a time-step convergence claim.
"""
from __future__ import annotations

import math

import numpy as np

from .assembly_tetra_transient import _assemble, _step
from .assembly_tetra_thermal_validation import (
    AssemblyTetraThermalError, identifier, keys, number, require, validate_request,
)

MAX_DEVICES = 512
MAX_MAPPING_ENTRIES = 20000
MAX_WEIGHT_VALUES = 2000000


class PreparedRetainedThermalStep:
    """Immutable preparation; advances do not retain or mutate thermal state."""

    def __init__(self, data, capacities, mappings, cancel):
        self._data = data
        require(not any(data['sources'].values()),
                'Prepared device losses require zero authored volumetric sources.')
        cell_by_id = {cell['id']: cell['vertices'] for cell in data['cells']}
        require(isinstance(mappings, dict) and 0 < len(mappings) <= MAX_DEVICES,
                'Device-to-cell mapping budget exceeded.')
        require(len(mappings) * len(data['xyz']) <= MAX_WEIGHT_VALUES,
                'Dense device mapping memory budget exceeded.')
        self._weights = {}
        entries = 0
        for device_id, distribution in mappings.items():
            identifier(device_id)
            require(isinstance(distribution, list) and distribution, 'Device distribution must be nonempty.')
            entries += len(distribution)
            require(entries <= MAX_MAPPING_ENTRIES, 'Device distribution entry budget exceeded.')
            seen, weights, total = set(), np.zeros(len(data['xyz'])), 0.
            for entry in distribution:
                keys(entry, ('cell_id', 'weight'))
                cell_id = identifier(entry['cell_id'])
                require(cell_id in cell_by_id and cell_id not in seen,
                        'Device distribution has unknown or duplicate cell.')
                seen.add(cell_id)
                fraction = number(entry['weight'], 'device cell weight', positive=True)
                total += fraction
                require(math.isfinite(total), 'Unrepresentable device distribution.')
                weights[cell_by_id[cell_id]] += fraction / 4
            require(abs(total - 1.) <= 1e-10, 'Device cell weights must sum to one.')
            weights /= total
            self._weights[device_id] = weights
        cancel()
        self._k, self._m, source, self._boundary = _assemble(data, capacities, cancel)
        require(not np.any(source), 'Prepared device losses require zero authored volumetric sources.')
        self._free = np.array([i for i in range(len(data['xyz'])) if i not in data['fixed']], dtype=int)
        self._fixed = np.array(sorted(data['fixed']), dtype=int)

    @property
    def device_ids(self):
        return tuple(self._weights)

    @property
    def node_count(self):
        return self._m.shape[0]

    def _temperature(self, values):
        require(isinstance(values, (list, tuple, np.ndarray)),
                'Nodal temperature must be a vector.')
        if isinstance(values, np.ndarray):
            require(values.ndim == 1, 'Nodal temperature must be one-dimensional.')
        require(len(values) == self.node_count,
                'Nodal temperature count mismatch.')
        if isinstance(values, np.ndarray):
            values = values.tolist()
        temperatures = np.array([number(value, 'temperature K', nonnegative=True) for value in values])
        require(all(temperatures[node] == fixed for node, fixed in self._data['fixed'].items()),
                'Nodal temperature must equal fixed boundary temperature.')
        if self._data['radiation']:
            require(np.all((temperatures > 0) & (temperatures <= 10000)),
                    'Radiation temperature range must be (0, 10000] K.')
        return temperatures

    def validate_temperature(self, node_temperatures_k):
        """Return an independent admitted Kelvin vector, including fixed-node checks."""
        return self._temperature(node_temperatures_k).tolist()

    def device_temperatures_k(self, node_temperatures_k):
        """Transpose gather of the normalized device energy-deposition map."""
        temperatures = self._temperature(node_temperatures_k)
        return {device_id: float(weights @ temperatures)
                for device_id, weights in self._weights.items()}

    def advance(self, old_temperature_k, dt_s, device_energies_j, *, cancel_check=None):
        """Advance one backward-Euler step; all signed boundary terms are explicit.

        device_energies_j must contain every prepared device exactly once.
        Cancellation raises AssemblyTetraThermalError and leaves no changed state.
        """
        def cancel():
            require(cancel_check is None or not cancel_check(),
                    'THERMAL_STEP_CANCELLED: thermal step cancelled.')

        try:
            with np.errstate(over='raise', invalid='raise', divide='raise'):
                cancel()
                old = self._temperature(old_temperature_k)
                dt = number(dt_s, 'time step s', positive=True)
                require(isinstance(device_energies_j, dict) and
                        set(device_energies_j) == set(self._weights),
                        'Device energies must match the complete prepared mapping.')
                energies = {device_id: number(value, 'device energy J', nonnegative=True)
                            for device_id, value in device_energies_j.items()}
                nodal_energy = np.zeros(self.node_count)
                for device_id, energy in energies.items():
                    nodal_energy += self._weights[device_id] * energy
                require(np.isfinite(nodal_energy).all(), 'Unrepresentable nodal device energy.')
                load = self._boundary + nodal_energy / dt
                require(np.isfinite(load).all(), 'Unrepresentable thermal load.')
                new, radiation, reactions, newton, cg, relative = _step(
                    self._k, self._m, old, dt, load, self._data, self._free, cancel)
                require(np.isfinite(new).all() and np.all(new >= 0), 'Invalid thermal step temperature.')
                storage = float(np.sum(self._m @ (new - old)))
                source = float(sum(energies.values()))
                flux = dt * sum(area * value for _, area, value in self._data['fluxes'])
                reaction = dt * float(np.sum(reactions[self._fixed]))
                convection = dt * sum(area * h * (float(np.mean(new[list(face)])) - ambient)
                                      for face, area, h, ambient in self._data['convection'])
                radiated = dt * float(np.sum(radiation))
                imbalance = source + flux + reaction - convection - radiated - storage
                scale = max(sum(abs(x) for x in (source, flux, reaction, convection, radiated, storage)), 1e-30)
                tolerance = 1e-8 * scale + 128 * np.finfo(float).eps * dt * float(np.sum(
                    np.abs(self._k + self._m / dt) @ np.abs(new)))
                require(math.isfinite(imbalance) and abs(imbalance) <= tolerance,
                        'Thermal step energy balance tolerance exceeded.')
                cancel()
                return {
                    'node_temperatures_k': new.tolist(),
                    'device_temperatures_k': {key: float(weights @ new) for key, weights in self._weights.items()},
                    'energy_balance': {
                        'source_j': source, 'prescribed_flux_inward_j': float(flux),
                        'temperature_reaction_inward_j': reaction,
                        'convection_outward_j': float(convection),
                        'radiation_outward_j': radiated, 'stored_energy_change_j': storage,
                        'imbalance_j': float(imbalance), 'acceptance_tolerance_j': float(tolerance),
                    },
                    'diagnostics': {'method': 'backward_euler', 'capacity_matrix': 'consistent_P1',
                                    'newton_iterations': newton, 'cg_iterations': cg,
                                    'free_relative_residual': relative,
                                    'model_status': 'experimental'},
                }
        except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
            raise AssemblyTetraThermalError('Thermal step is numerically unrepresentable.') from exc


def prepare_retained_thermal_step(thermal_request, material_heat_capacity,
                                  device_cell_fractions, *, cancel_check=None):
    """Validate a zero-source thermal request and prepare reusable sparse matrices.

    material_heat_capacity is a list of {material_id, density_kg_m3,
    specific_heat_j_kgk}; device_cell_fractions maps device IDs to lists of
    {cell_id, weight}. Density is kg/m3, heat capacity J/(kg K), dt seconds,
    and each subsequent device energy Joules over that step.
    """
    def cancel():
        require(cancel_check is None or not cancel_check(),
                'THERMAL_STEP_CANCELLED: thermal preparation cancelled.')

    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            cancel()
            data = validate_request(thermal_request)
            require(isinstance(material_heat_capacity, list) and
                    len(material_heat_capacity) == len(data['tensors']),
                    'Heat capacity required exactly once per material.')
            capacities = {}
            for record in material_heat_capacity:
                keys(record, ('material_id', 'density_kg_m3', 'specific_heat_j_kgk'))
                mid = identifier(record['material_id'])
                require(mid in data['tensors'] and mid not in capacities,
                        'Unknown or duplicate heat-capacity material.')
                capacity = (number(record['density_kg_m3'], 'density', positive=True) *
                            number(record['specific_heat_j_kgk'], 'specific heat', positive=True))
                require(math.isfinite(capacity) and capacity > 0,
                        'Unrepresentable volumetric heat capacity.')
                capacities[mid] = capacity
            cancel()
            return PreparedRetainedThermalStep(data, capacities, device_cell_fractions, cancel)
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        raise AssemblyTetraThermalError('Thermal preparation is numerically unrepresentable.') from exc
