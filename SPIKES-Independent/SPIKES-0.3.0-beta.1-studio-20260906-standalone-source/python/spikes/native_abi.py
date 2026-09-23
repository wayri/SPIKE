"""Explicit ctypes bridge to the owned SPIKES C ABI.

Loading is deliberately opt-in: callers provide an exact local shared-library
path.  Importing :mod:`python.spikes` never searches for or loads native code.
"""

from __future__ import annotations

import ctypes
import math
from pathlib import Path
from typing import Any


SPIKES_ABI_VERSION = 1
SPIKES_TRANSIENT_API_VERSION = 1
SPIKES_LINEAR_SOLVER_API_VERSION = 1


class _TransientOptions(ctypes.Structure):
    _fields_ = (
        ("struct_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_size_t),
        ("time_step_s", ctypes.c_double),
        ("stop_time_s", ctypes.c_double),
        ("max_steps", ctypes.c_size_t),
        ("initialize_from_operating_point", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8 * 7),
        ("max_newton_iterations", ctypes.c_size_t),
        ("max_backtracks", ctypes.c_size_t),
        ("absolute_tolerance", ctypes.c_double),
        ("relative_tolerance", ctypes.c_double),
    )


class _LinearSolverOptions(ctypes.Structure):
    _fields_ = (
        ("struct_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_size_t),
        ("method", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("max_iterations", ctypes.c_size_t),
        ("absolute_tolerance", ctypes.c_double),
        ("relative_tolerance", ctypes.c_double),
        ("threads", ctypes.c_size_t),
    )


class _PwlPoint(ctypes.Structure):
    _fields_ = (("time_s", ctypes.c_double), ("value", ctypes.c_double))


class _WbgFetElectrothermalModel(ctypes.Structure):
    _fields_ = (
        ("struct_version", ctypes.c_uint32),
        ("technology", ctypes.c_uint32),
        ("struct_size", ctypes.c_size_t),
        ("reserved", ctypes.c_uint32),
        ("threshold_voltage_v", ctypes.c_double),
        ("transconductance_a_per_v2", ctypes.c_double),
        ("channel_length_modulation_per_v", ctypes.c_double),
        ("mobility_temperature_exponent", ctypes.c_double),
        ("threshold_temperature_coefficient_v_per_k", ctypes.c_double),
        ("off_conductance_s", ctypes.c_double),
        ("reverse_conduction_threshold_v", ctypes.c_double),
        ("reverse_conductance_s", ctypes.c_double),
        ("body_diode_saturation_current_a", ctypes.c_double),
        ("body_diode_emission_coefficient", ctypes.c_double),
        ("breakdown_voltage_v", ctypes.c_double),
        ("breakdown_temperature_coefficient_v_per_k", ctypes.c_double),
        ("avalanche_current_scale_a", ctypes.c_double),
        ("avalanche_slope_v", ctypes.c_double),
        ("gate_leakage_conductance_s", ctypes.c_double),
        ("gate_source_capacitance_f", ctypes.c_double),
        ("gate_drain_capacitance_f", ctypes.c_double),
        ("drain_source_capacitance_f", ctypes.c_double),
        ("ambient_temperature_k", ctypes.c_double),
        ("thermal_resistance_k_per_w", ctypes.c_double),
        ("minimum_temperature_k", ctypes.c_double),
        ("maximum_temperature_k", ctypes.c_double),
        ("maximum_absolute_voltage_v", ctypes.c_double),
        ("maximum_absolute_current_a", ctypes.c_double),
        ("thermal_capacitance_j_per_k", ctypes.c_double),
    )


class NativeABIError(RuntimeError):
    """A native call failed or the requested library is incompatible."""


def _text(value: Any, label: str) -> bytes:
    normalized = str(value)
    if not normalized or "\x00" in normalized:
        raise ValueError(f"{label} must be non-empty text without NUL bytes.")
    return normalized.encode("utf-8")


def _finite(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    return number


class NativeLibrary:
    """One verified SPIKES shared library with bound ABI declarations."""

    def __init__(self, path: str | Path) -> None:
        candidate = Path(path).expanduser().resolve(strict=True)
        if not candidate.is_file():
            raise ValueError("SPIKES native library path must name a regular file.")
        if candidate.suffix.lower() not in {".dll", ".so", ".dylib"}:
            raise ValueError("SPIKES native library must be a DLL, SO, or dylib file.")
        try:
            library = ctypes.CDLL(str(candidate))
        except OSError as exc:
            raise NativeABIError(f"Unable to load SPIKES native library: {exc}") from exc
        self.path = candidate
        self._library = library
        self._bind()
        version = int(library.spikes_abi_version())
        if version != SPIKES_ABI_VERSION:
            raise NativeABIError(
                f"SPIKES ABI mismatch: Python requires {SPIKES_ABI_VERSION}, library reports {version}."
            )

    def _bind(self) -> None:
        lib = self._library
        pointer = ctypes.c_void_p
        char_pointer = ctypes.c_char_p
        lib.spikes_abi_version.argtypes = ()
        lib.spikes_abi_version.restype = ctypes.c_uint32
        lib.spikes_last_error.argtypes = ()
        lib.spikes_last_error.restype = char_pointer
        lib.spikes_circuit_create.argtypes = (ctypes.POINTER(pointer),)
        lib.spikes_circuit_create.restype = ctypes.c_int
        lib.spikes_circuit_destroy.argtypes = (pointer,)
        lib.spikes_circuit_destroy.restype = None
        for name in (
            "spikes_circuit_add_resistor",
            "spikes_circuit_add_current_source",
            "spikes_circuit_add_voltage_source",
        ):
            function = getattr(lib, name)
            function.argtypes = (pointer, char_pointer, char_pointer, char_pointer, ctypes.c_double)
            function.restype = ctypes.c_int
        lib.spikes_circuit_add_diode.argtypes = (
            pointer, char_pointer, char_pointer, char_pointer,
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
        )
        lib.spikes_circuit_add_diode.restype = ctypes.c_int
        self.dynamic_diode_available = hasattr(
            lib, "spikes_circuit_add_dynamic_diode"
        )
        if self.dynamic_diode_available:
            lib.spikes_circuit_add_dynamic_diode.argtypes = (
                pointer, char_pointer, char_pointer, char_pointer,
                ctypes.c_double, ctypes.c_double, ctypes.c_double,
                ctypes.c_double, ctypes.c_double, ctypes.c_double,
            )
            lib.spikes_circuit_add_dynamic_diode.restype = ctypes.c_int
        self.electrothermal_resistor_available = hasattr(
            lib, "spikes_circuit_add_electrothermal_resistor"
        )
        if self.electrothermal_resistor_available:
            lib.spikes_circuit_add_electrothermal_resistor.argtypes = (
                pointer, char_pointer, char_pointer, char_pointer,
                char_pointer, ctypes.c_double, ctypes.c_double,
                ctypes.c_double, ctypes.c_double, ctypes.c_double,
                ctypes.c_double, ctypes.c_double,
            )
            lib.spikes_circuit_add_electrothermal_resistor.restype = ctypes.c_int
        self.saturating_inductor_available = hasattr(
            lib, "spikes_circuit_add_saturating_inductor"
        )
        if self.saturating_inductor_available:
            lib.spikes_circuit_add_saturating_inductor.argtypes = (
                pointer, char_pointer, char_pointer, char_pointer,
                ctypes.c_double, ctypes.c_double, ctypes.c_double,
                ctypes.c_double,
            )
            lib.spikes_circuit_add_saturating_inductor.restype = ctypes.c_int
        lib.spikes_solve_operating_point.argtypes = (pointer, ctypes.POINTER(pointer))
        lib.spikes_solve_operating_point.restype = ctypes.c_int
        lib.spikes_result_destroy.argtypes = (pointer,)
        lib.spikes_result_destroy.restype = None
        lib.spikes_result_status.argtypes = (pointer,)
        lib.spikes_result_status.restype = ctypes.c_int
        lib.spikes_result_message.argtypes = (pointer,)
        lib.spikes_result_message.restype = char_pointer
        for name in (
            "spikes_result_node_voltage",
            "spikes_result_element_current",
            "spikes_result_element_power",
        ):
            function = getattr(lib, name)
            function.argtypes = (pointer, char_pointer, ctypes.POINTER(ctypes.c_double))
            function.restype = ctypes.c_int
        lib.spikes_result_diagnostics.argtypes = (
            pointer,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_double),
        )
        lib.spikes_result_diagnostics.restype = ctypes.c_int
        linear_symbols = (
            "spikes_linear_solver_options_init",
            "spikes_solve_operating_point_with_linear_solver",
            "spikes_result_linear_solver_diagnostics",
        )
        linear_present = tuple(hasattr(lib, name) for name in linear_symbols)
        if any(linear_present) and not all(linear_present):
            raise NativeABIError("SPIKES library exposes an incomplete linear-solver API.")
        self.linear_solver_options_available = all(linear_present)
        self.sparse_solver_diagnostics_available = hasattr(
            lib, "spikes_result_sparse_solver_diagnostics"
        )
        if self.linear_solver_options_available:
            lib.spikes_linear_solver_options_init.argtypes = (
                ctypes.POINTER(_LinearSolverOptions),
            )
            lib.spikes_linear_solver_options_init.restype = ctypes.c_int
            lib.spikes_solve_operating_point_with_linear_solver.argtypes = (
                pointer, ctypes.POINTER(_LinearSolverOptions),
                ctypes.POINTER(pointer),
            )
            lib.spikes_solve_operating_point_with_linear_solver.restype = ctypes.c_int
            lib.spikes_result_linear_solver_diagnostics.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_uint32),
                ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
            )
            lib.spikes_result_linear_solver_diagnostics.restype = ctypes.c_int
        if self.sparse_solver_diagnostics_available:
            lib.spikes_result_sparse_solver_diagnostics.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
            )
            lib.spikes_result_sparse_solver_diagnostics.restype = ctypes.c_int
        self.voltage_controlled_switch_available = hasattr(
            lib, "spikes_circuit_add_voltage_controlled_switch"
        )
        if self.voltage_controlled_switch_available:
            lib.spikes_circuit_add_voltage_controlled_switch.argtypes = (
                pointer, char_pointer, char_pointer, char_pointer,
                char_pointer, char_pointer, ctypes.c_double, ctypes.c_double,
                ctypes.c_double, ctypes.c_double,
            )
            lib.spikes_circuit_add_voltage_controlled_switch.restype = ctypes.c_int
        self.mosfet_level1_available = hasattr(
            lib, "spikes_circuit_add_mosfet_level1"
        )
        if self.mosfet_level1_available:
            lib.spikes_circuit_add_mosfet_level1.argtypes = (
                pointer, char_pointer, char_pointer, char_pointer,
                char_pointer, char_pointer,
                ctypes.c_double, ctypes.c_double, ctypes.c_double,
                ctypes.c_double, ctypes.c_double, ctypes.c_double,
                ctypes.c_double,
            )
            lib.spikes_circuit_add_mosfet_level1.restype = ctypes.c_int
        self.bjt_ebers_moll_available = hasattr(
            lib, "spikes_circuit_add_bjt_ebers_moll"
        )
        if self.bjt_ebers_moll_available:
            lib.spikes_circuit_add_bjt_ebers_moll.argtypes = (
                pointer, char_pointer, char_pointer, char_pointer, char_pointer,
                ctypes.c_double, ctypes.c_double, ctypes.c_double,
                ctypes.c_double, ctypes.c_double,
            )
            lib.spikes_circuit_add_bjt_ebers_moll.restype = ctypes.c_int
        wbg_symbols = (
            "spikes_wbg_fet_electrothermal_model_init",
            "spikes_circuit_add_wbg_fet_electrothermal",
        )
        wbg_present = tuple(hasattr(lib, name) for name in wbg_symbols)
        if any(wbg_present) and not all(wbg_present):
            raise NativeABIError(
                "SPIKES library exposes an incomplete electrothermal WBG API."
            )
        self.wbg_fet_electrothermal_available = all(wbg_present)
        if self.wbg_fet_electrothermal_available:
            lib.spikes_wbg_fet_electrothermal_model_init.argtypes = (
                ctypes.POINTER(_WbgFetElectrothermalModel), ctypes.c_uint32,
            )
            lib.spikes_wbg_fet_electrothermal_model_init.restype = ctypes.c_int
            lib.spikes_circuit_add_wbg_fet_electrothermal.argtypes = (
                pointer, char_pointer, char_pointer, char_pointer,
                char_pointer, char_pointer, char_pointer,
                ctypes.POINTER(_WbgFetElectrothermalModel),
            )
            lib.spikes_circuit_add_wbg_fet_electrothermal.restype = ctypes.c_int
        transient_symbols = (
            "spikes_circuit_add_capacitor", "spikes_circuit_add_inductor",
            "spikes_transient_options_init", "spikes_solve_transient",
            "spikes_transient_result_destroy", "spikes_transient_result_status",
            "spikes_transient_result_message", "spikes_transient_result_point_count",
            "spikes_transient_result_point_time", "spikes_transient_result_node_voltage",
            "spikes_transient_result_element_current", "spikes_transient_result_element_power",
            "spikes_transient_result_diagnostics",
        )
        present = tuple(hasattr(lib, name) for name in transient_symbols)
        if any(present) and not all(present):
            raise NativeABIError("SPIKES library exposes an incomplete transient API.")
        self.transient_available = all(present)
        self.waveform_sources_available = False
        self.transient_session_available = False
        if not self.transient_available:
            return
        for name in ("spikes_circuit_add_capacitor", "spikes_circuit_add_inductor"):
            function = getattr(lib, name)
            function.argtypes = (
                pointer, char_pointer, char_pointer, char_pointer,
                ctypes.c_double, ctypes.c_double,
            )
            function.restype = ctypes.c_int
        lib.spikes_transient_options_init.argtypes = (ctypes.POINTER(_TransientOptions),)
        lib.spikes_transient_options_init.restype = ctypes.c_int
        lib.spikes_solve_transient.argtypes = (
            pointer, ctypes.POINTER(_TransientOptions), ctypes.POINTER(pointer),
        )
        lib.spikes_solve_transient.restype = ctypes.c_int
        self.integration_method_available = hasattr(
            lib, "spikes_solve_transient_with_method"
        )
        if self.integration_method_available:
            lib.spikes_solve_transient_with_method.argtypes = (
                pointer, ctypes.POINTER(_TransientOptions), ctypes.c_uint32,
                ctypes.POINTER(pointer),
            )
            lib.spikes_solve_transient_with_method.restype = ctypes.c_int
        self.adaptive_transient_available = hasattr(
            lib, "spikes_solve_transient_adaptive"
        )
        if self.adaptive_transient_available:
            lib.spikes_solve_transient_adaptive.argtypes = (
                pointer, ctypes.POINTER(_TransientOptions), ctypes.c_uint32,
                ctypes.c_uint8, ctypes.c_double, ctypes.c_double,
                ctypes.c_double, ctypes.c_size_t, ctypes.POINTER(pointer),
            )
            lib.spikes_solve_transient_adaptive.restype = ctypes.c_int
        lib.spikes_transient_result_destroy.argtypes = (pointer,)
        lib.spikes_transient_result_destroy.restype = None
        lib.spikes_transient_result_status.argtypes = (pointer,)
        lib.spikes_transient_result_status.restype = ctypes.c_int
        lib.spikes_transient_result_message.argtypes = (pointer,)
        lib.spikes_transient_result_message.restype = char_pointer
        lib.spikes_transient_result_point_count.argtypes = (pointer,)
        lib.spikes_transient_result_point_count.restype = ctypes.c_size_t
        lib.spikes_transient_result_point_time.argtypes = (
            pointer, ctypes.c_size_t, ctypes.POINTER(ctypes.c_double),
        )
        lib.spikes_transient_result_point_time.restype = ctypes.c_int
        for name in (
            "spikes_transient_result_node_voltage",
            "spikes_transient_result_element_current",
            "spikes_transient_result_element_power",
        ):
            function = getattr(lib, name)
            function.argtypes = (
                pointer, ctypes.c_size_t, char_pointer, ctypes.POINTER(ctypes.c_double),
            )
            function.restype = ctypes.c_int
        lib.spikes_transient_result_diagnostics.argtypes = (
            pointer,
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
        )
        lib.spikes_transient_result_diagnostics.restype = ctypes.c_int
        self.breakpoint_diagnostics_available = hasattr(
            lib, "spikes_transient_result_breakpoint_steps"
        )
        if self.breakpoint_diagnostics_available:
            lib.spikes_transient_result_breakpoint_steps.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_size_t),
            )
            lib.spikes_transient_result_breakpoint_steps.restype = ctypes.c_int
        self.factorization_diagnostics_available = hasattr(
            lib, "spikes_transient_result_factorization_diagnostics"
        )
        if self.factorization_diagnostics_available:
            lib.spikes_transient_result_factorization_diagnostics.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
            )
            lib.spikes_transient_result_factorization_diagnostics.restype = ctypes.c_int
        self.integration_diagnostics_available = hasattr(
            lib, "spikes_transient_result_integration_diagnostics"
        )
        if self.integration_diagnostics_available:
            lib.spikes_transient_result_integration_diagnostics.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(ctypes.c_size_t),
            )
            lib.spikes_transient_result_integration_diagnostics.restype = ctypes.c_int
        self.bdf2_available = hasattr(lib, "spikes_transient_result_bdf2_steps")
        if self.bdf2_available:
            lib.spikes_transient_result_bdf2_steps.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_size_t),
            )
            lib.spikes_transient_result_bdf2_steps.restype = ctypes.c_int
        self.lte_diagnostics_available = hasattr(
            lib, "spikes_transient_result_lte_diagnostics"
        )
        if self.lte_diagnostics_available:
            lib.spikes_transient_result_lte_diagnostics.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
                ctypes.POINTER(ctypes.c_double),
            )
            lib.spikes_transient_result_lte_diagnostics.restype = ctypes.c_int
        self.sparse_lte_diagnostics_available = hasattr(
            lib, "spikes_transient_result_sparse_lte_diagnostics"
        )
        if self.sparse_lte_diagnostics_available:
            lib.spikes_transient_result_sparse_lte_diagnostics.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
            )
            lib.spikes_transient_result_sparse_lte_diagnostics.restype = ctypes.c_int
        session_symbols = (
            "spikes_transient_session_create",
            "spikes_transient_session_destroy",
            "spikes_transient_session_set_source_value",
            "spikes_transient_session_step",
            "spikes_transient_session_status",
            "spikes_transient_session_message",
            "spikes_transient_session_position",
            "spikes_transient_session_node_voltage",
            "spikes_transient_session_element_current",
            "spikes_transient_session_element_power",
            "spikes_transient_session_diagnostics",
            "spikes_transient_session_checkpoint_create",
            "spikes_transient_checkpoint_destroy",
            "spikes_transient_session_restore",
        )
        session_present = tuple(hasattr(lib, name) for name in session_symbols)
        if any(session_present) and not all(session_present):
            raise NativeABIError(
                "SPIKES library exposes an incomplete persistent transient-session API."
            )
        self.transient_session_available = all(session_present)
        self.session_factorization_diagnostics_available = False
        self.session_integration_method_available = False
        self.session_integration_diagnostics_available = False
        self.session_bdf2_available = False
        self.session_element_voltage_available = False
        if self.transient_session_available:
            lib.spikes_transient_session_create.argtypes = (
                pointer, ctypes.POINTER(_TransientOptions), ctypes.POINTER(pointer),
            )
            lib.spikes_transient_session_create.restype = ctypes.c_int
            self.session_integration_method_available = hasattr(
                lib, "spikes_transient_session_create_with_method"
            )
            if self.session_integration_method_available:
                lib.spikes_transient_session_create_with_method.argtypes = (
                    pointer, ctypes.POINTER(_TransientOptions), ctypes.c_uint32,
                    ctypes.POINTER(pointer),
                )
                lib.spikes_transient_session_create_with_method.restype = ctypes.c_int
            lib.spikes_transient_session_destroy.argtypes = (pointer,)
            lib.spikes_transient_session_destroy.restype = None
            lib.spikes_transient_session_set_source_value.argtypes = (
                pointer, char_pointer, ctypes.c_double,
            )
            lib.spikes_transient_session_set_source_value.restype = ctypes.c_int
            lib.spikes_transient_session_step.argtypes = (
                pointer, ctypes.c_double, ctypes.POINTER(ctypes.c_uint8),
            )
            lib.spikes_transient_session_step.restype = ctypes.c_int
            lib.spikes_transient_session_status.argtypes = (pointer,)
            lib.spikes_transient_session_status.restype = ctypes.c_int
            lib.spikes_transient_session_message.argtypes = (pointer,)
            lib.spikes_transient_session_message.restype = char_pointer
            lib.spikes_transient_session_position.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_double),
                ctypes.POINTER(ctypes.c_size_t),
            )
            lib.spikes_transient_session_position.restype = ctypes.c_int
            for name in (
                "spikes_transient_session_node_voltage",
                "spikes_transient_session_element_current",
                "spikes_transient_session_element_power",
            ):
                function = getattr(lib, name)
                function.argtypes = (
                    pointer, char_pointer, ctypes.POINTER(ctypes.c_double),
                )
                function.restype = ctypes.c_int
            self.session_element_voltage_available = hasattr(
                lib, "spikes_transient_session_element_voltage"
            )
            if self.session_element_voltage_available:
                lib.spikes_transient_session_element_voltage.argtypes = (
                    pointer, char_pointer, ctypes.POINTER(ctypes.c_double),
                )
                lib.spikes_transient_session_element_voltage.restype = ctypes.c_int
            lib.spikes_transient_session_diagnostics.argtypes = (
                pointer, ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(ctypes.c_double),
            )
            lib.spikes_transient_session_diagnostics.restype = ctypes.c_int
            self.session_factorization_diagnostics_available = hasattr(
                lib, "spikes_transient_session_factorization_diagnostics"
            )
            if self.session_factorization_diagnostics_available:
                lib.spikes_transient_session_factorization_diagnostics.argtypes = (
                    pointer, ctypes.POINTER(ctypes.c_size_t),
                    ctypes.POINTER(ctypes.c_size_t),
                )
                lib.spikes_transient_session_factorization_diagnostics.restype = ctypes.c_int
            self.session_integration_diagnostics_available = hasattr(
                lib, "spikes_transient_session_integration_diagnostics"
            )
            if self.session_integration_diagnostics_available:
                lib.spikes_transient_session_integration_diagnostics.argtypes = (
                    pointer, ctypes.POINTER(ctypes.c_size_t),
                    ctypes.POINTER(ctypes.c_size_t),
                )
                lib.spikes_transient_session_integration_diagnostics.restype = ctypes.c_int
            self.session_bdf2_available = hasattr(
                lib, "spikes_transient_session_bdf2_steps"
            )
            if self.session_bdf2_available:
                lib.spikes_transient_session_bdf2_steps.argtypes = (
                    pointer, ctypes.POINTER(ctypes.c_size_t),
                )
                lib.spikes_transient_session_bdf2_steps.restype = ctypes.c_int
            lib.spikes_transient_session_checkpoint_create.argtypes = (
                pointer, ctypes.POINTER(pointer),
            )
            lib.spikes_transient_session_checkpoint_create.restype = ctypes.c_int
            lib.spikes_transient_checkpoint_destroy.argtypes = (pointer,)
            lib.spikes_transient_checkpoint_destroy.restype = None
            lib.spikes_transient_session_restore.argtypes = (pointer, pointer)
            lib.spikes_transient_session_restore.restype = ctypes.c_int
        waveform_symbols = (
            "spikes_circuit_add_pulse_current_source",
            "spikes_circuit_add_pulse_voltage_source",
            "spikes_circuit_add_pwl_current_source",
            "spikes_circuit_add_pwl_voltage_source",
        )
        waveform_present = tuple(hasattr(lib, name) for name in waveform_symbols)
        if any(waveform_present) and not all(waveform_present):
            raise NativeABIError("SPIKES library exposes an incomplete waveform-source API.")
        self.waveform_sources_available = all(waveform_present)
        if self.waveform_sources_available:
            for name in waveform_symbols[:2]:
                function = getattr(lib, name)
                function.argtypes = (
                    pointer, char_pointer, char_pointer, char_pointer,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    ctypes.c_double,
                )
                function.restype = ctypes.c_int
            for name in waveform_symbols[2:]:
                function = getattr(lib, name)
                function.argtypes = (
                    pointer, char_pointer, char_pointer, char_pointer,
                    ctypes.POINTER(_PwlPoint), ctypes.c_size_t,
                )
                function.restype = ctypes.c_int

    def _error(self) -> str:
        raw = self._library.spikes_last_error()
        return raw.decode("utf-8", errors="replace") if raw else "unspecified native error"

    def _check(self, code: int, operation: str) -> None:
        if int(code) != 0:
            raise NativeABIError(f"{operation} failed ({int(code)}): {self._error()}")

    def circuit(self) -> "NativeCircuit":
        handle = ctypes.c_void_p()
        self._check(self._library.spikes_circuit_create(ctypes.byref(handle)), "circuit creation")
        if not handle.value:
            raise NativeABIError("circuit creation returned a null handle")
        return NativeCircuit(self, handle)


class NativeCircuit:
    """Context-managed owner of a native circuit handle."""

    def __init__(self, library: NativeLibrary, handle: ctypes.c_void_p) -> None:
        self.library = library
        self._handle = handle

    def _open_handle(self) -> ctypes.c_void_p:
        if not self._handle.value:
            raise NativeABIError("native circuit is closed")
        return self._handle

    def close(self) -> None:
        if self._handle.value:
            self.library._library.spikes_circuit_destroy(self._handle)
            self._handle = ctypes.c_void_p()

    def __enter__(self) -> "NativeCircuit":
        self._open_handle()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _add(self, function_name: str, element_id: str, positive: str, negative: str, value: float) -> None:
        function = getattr(self.library._library, function_name)
        code = function(
            self._open_handle(), _text(element_id, "element id"),
            _text(positive, "positive node"), _text(negative, "negative node"),
            _finite(value, "element value"),
        )
        self.library._check(code, f"adding {element_id}")

    def add_resistor(self, element_id: str, positive: str, negative: str, resistance_ohm: float) -> None:
        self._add("spikes_circuit_add_resistor", element_id, positive, negative, resistance_ohm)

    def add_current_source(self, element_id: str, positive: str, negative: str, current_a: float) -> None:
        self._add("spikes_circuit_add_current_source", element_id, positive, negative, current_a)

    def add_voltage_source(self, element_id: str, positive: str, negative: str, voltage_v: float) -> None:
        self._add("spikes_circuit_add_voltage_source", element_id, positive, negative, voltage_v)

    def _add_pulse_source(
        self, function_name: str, element_id: str, positive: str, negative: str,
        *, initial_value: float, pulsed_value: float, delay_s: float,
        rise_time_s: float, fall_time_s: float, pulse_width_s: float,
        period_s: float,
    ) -> None:
        if not self.library.waveform_sources_available:
            raise NativeABIError("Loaded SPIKES library does not expose waveform sources.")
        values = (
            initial_value, pulsed_value, delay_s, rise_time_s, fall_time_s,
            pulse_width_s, period_s,
        )
        code = getattr(self.library._library, function_name)(
            self._open_handle(), _text(element_id, "element id"),
            _text(positive, "positive node"), _text(negative, "negative node"),
            *(_finite(value, "PULSE parameter") for value in values),
        )
        self.library._check(code, f"adding {element_id}")

    def add_pulse_voltage_source(
        self, element_id: str, positive: str, negative: str, *,
        initial_value: float, pulsed_value: float, delay_s: float = 0.0,
        rise_time_s: float = 0.0, fall_time_s: float = 0.0,
        pulse_width_s: float, period_s: float,
    ) -> None:
        self._add_pulse_source(
            "spikes_circuit_add_pulse_voltage_source", element_id, positive,
            negative, initial_value=initial_value, pulsed_value=pulsed_value,
            delay_s=delay_s, rise_time_s=rise_time_s,
            fall_time_s=fall_time_s, pulse_width_s=pulse_width_s,
            period_s=period_s,
        )

    def add_pulse_current_source(
        self, element_id: str, positive: str, negative: str, *,
        initial_value: float, pulsed_value: float, delay_s: float = 0.0,
        rise_time_s: float = 0.0, fall_time_s: float = 0.0,
        pulse_width_s: float, period_s: float,
    ) -> None:
        self._add_pulse_source(
            "spikes_circuit_add_pulse_current_source", element_id, positive,
            negative, initial_value=initial_value, pulsed_value=pulsed_value,
            delay_s=delay_s, rise_time_s=rise_time_s,
            fall_time_s=fall_time_s, pulse_width_s=pulse_width_s,
            period_s=period_s,
        )

    def _add_pwl_source(
        self, function_name: str, element_id: str, positive: str, negative: str,
        points: Any,
    ) -> None:
        if not self.library.waveform_sources_available:
            raise NativeABIError("Loaded SPIKES library does not expose waveform sources.")
        normalized = tuple(
            (_finite(point[0], "PWL time"), _finite(point[1], "PWL value"))
            for point in points
        )
        if not normalized:
            raise ValueError("PWL source requires at least one point.")
        native_points = (_PwlPoint * len(normalized))(
            *(_PwlPoint(time_s, value) for time_s, value in normalized)
        )
        code = getattr(self.library._library, function_name)(
            self._open_handle(), _text(element_id, "element id"),
            _text(positive, "positive node"), _text(negative, "negative node"),
            native_points, len(normalized),
        )
        self.library._check(code, f"adding {element_id}")

    def add_pwl_voltage_source(
        self, element_id: str, positive: str, negative: str, points: Any,
    ) -> None:
        self._add_pwl_source(
            "spikes_circuit_add_pwl_voltage_source", element_id, positive,
            negative, points,
        )

    def add_pwl_current_source(
        self, element_id: str, positive: str, negative: str, points: Any,
    ) -> None:
        self._add_pwl_source(
            "spikes_circuit_add_pwl_current_source", element_id, positive,
            negative, points,
        )

    def add_voltage_controlled_switch(
        self, element_id: str, positive: str, negative: str,
        control_positive: str, control_negative: str, *,
        on_resistance_ohm: float = 1.0e-3,
        off_resistance_ohm: float = 1.0e9,
        threshold_voltage_v: float = 0.5,
        transition_voltage_v: float = 1.0e-3,
    ) -> None:
        if not self.library.voltage_controlled_switch_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose voltage-controlled switches."
            )
        code = self.library._library.spikes_circuit_add_voltage_controlled_switch(
            self._open_handle(), _text(element_id, "element id"),
            _text(positive, "positive node"), _text(negative, "negative node"),
            _text(control_positive, "control positive node"),
            _text(control_negative, "control negative node"),
            _finite(on_resistance_ohm, "switch on resistance"),
            _finite(off_resistance_ohm, "switch off resistance"),
            _finite(threshold_voltage_v, "switch threshold voltage"),
            _finite(transition_voltage_v, "switch transition voltage"),
        )
        self.library._check(code, f"adding {element_id}")

    def add_diode(
        self, element_id: str, anode: str, cathode: str, *,
        saturation_current_a: float = 1.0e-14,
        emission_coefficient: float = 1.0,
        temperature_k: float = 300.15,
    ) -> None:
        code = self.library._library.spikes_circuit_add_diode(
            self._open_handle(), _text(element_id, "element id"),
            _text(anode, "anode"), _text(cathode, "cathode"),
            _finite(saturation_current_a, "saturation current"),
            _finite(emission_coefficient, "emission coefficient"),
            _finite(temperature_k, "temperature"),
        )
        self.library._check(code, f"adding {element_id}")

    def add_dynamic_diode(
        self, element_id: str, anode: str, cathode: str, *,
        saturation_current_a: float = 1.0e-14,
        emission_coefficient: float = 1.0,
        temperature_k: float = 300.15,
        transit_time_s: float = 50.0e-9,
        junction_capacitance_f: float = 10.0e-12,
        initial_stored_charge_c: float = 0.0,
    ) -> None:
        """Add the native charge-control reverse-recovery diode."""

        if not self.library.dynamic_diode_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose dynamic diodes."
            )
        code = self.library._library.spikes_circuit_add_dynamic_diode(
            self._open_handle(), _text(element_id, "element id"),
            _text(anode, "anode"), _text(cathode, "cathode"),
            _finite(saturation_current_a, "saturation current"),
            _finite(emission_coefficient, "emission coefficient"),
            _finite(temperature_k, "temperature"),
            _finite(transit_time_s, "transit time"),
            _finite(junction_capacitance_f, "junction capacitance"),
            _finite(initial_stored_charge_c, "initial stored charge"),
        )
        self.library._check(code, f"adding {element_id}")

    def add_electrothermal_resistor(
        self, element_id: str, positive: str, negative: str, thermal: str, *,
        resistance_ohm: float = 1.0,
        temperature_coefficient_per_k: float = 3.9e-3,
        ambient_temperature_k: float = 300.15,
        thermal_resistance_k_per_w: float = 10.0,
        thermal_capacitance_j_per_k: float = 1.0e-3,
        minimum_temperature_k: float = 200.0,
        maximum_temperature_k: float = 1000.0,
    ) -> None:
        """Add the native coupled R(T)-Rth-Cth DAE device."""

        if not self.library.electrothermal_resistor_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose electrothermal resistors."
            )
        code = self.library._library.spikes_circuit_add_electrothermal_resistor(
            self._open_handle(), _text(element_id, "element id"),
            _text(positive, "positive node"),
            _text(negative, "negative node"),
            _text(thermal, "thermal node"),
            _finite(resistance_ohm, "resistance"),
            _finite(temperature_coefficient_per_k, "temperature coefficient"),
            _finite(ambient_temperature_k, "ambient temperature"),
            _finite(thermal_resistance_k_per_w, "thermal resistance"),
            _finite(thermal_capacitance_j_per_k, "thermal capacitance"),
            _finite(minimum_temperature_k, "minimum temperature"),
            _finite(maximum_temperature_k, "maximum temperature"),
        )
        self.library._check(code, f"adding {element_id}")

    def add_mosfet_level1(
        self, element_id: str, drain: str, gate: str, source: str, bulk: str,
        *, threshold_voltage_v: float = 1.0,
        transconductance_a_per_v2: float = 1.0e-3,
        channel_length_modulation_per_v: float = 0.0,
        body_effect_sqrt_v: float = 0.0,
        surface_potential_v: float = 0.6,
        width_over_length: float = 1.0,
        off_conductance_s: float = 1.0e-12,
    ) -> None:
        if not self.library.mosfet_level1_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose native MOSFET Level-1."
            )
        code = self.library._library.spikes_circuit_add_mosfet_level1(
            self._open_handle(), _text(element_id, "element id"),
            _text(drain, "drain"), _text(gate, "gate"),
            _text(source, "source"), _text(bulk, "bulk"),
            _finite(threshold_voltage_v, "threshold voltage"),
            _finite(transconductance_a_per_v2, "transconductance parameter"),
            _finite(channel_length_modulation_per_v, "channel length modulation"),
            _finite(body_effect_sqrt_v, "body effect"),
            _finite(surface_potential_v, "surface potential"),
            _finite(width_over_length, "width over length"),
            _finite(off_conductance_s, "off conductance"),
        )
        self.library._check(code, f"adding {element_id}")

    def add_bjt_ebers_moll(
        self, element_id: str, collector: str, base: str, emitter: str,
        *, saturation_current_a: float = 1.0e-15,
        forward_alpha: float = 0.99, reverse_alpha: float = 0.5,
        emission_coefficient: float = 1.0,
        temperature_k: float = 300.15,
    ) -> None:
        if not self.library.bjt_ebers_moll_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose native Ebers-Moll BJT."
            )
        code = self.library._library.spikes_circuit_add_bjt_ebers_moll(
            self._open_handle(), _text(element_id, "element id"),
            _text(collector, "collector"), _text(base, "base"),
            _text(emitter, "emitter"),
            _finite(saturation_current_a, "saturation current"),
            _finite(forward_alpha, "forward alpha"),
            _finite(reverse_alpha, "reverse alpha"),
            _finite(emission_coefficient, "emission coefficient"),
            _finite(temperature_k, "temperature"),
        )
        self.library._check(code, f"adding {element_id}")

    def add_wbg_fet_electrothermal(
        self, element_id: str, drain: str, gate: str, source: str, bulk: str,
        thermal: str, *, technology: str = "gan_hemt", **parameters: float,
    ) -> None:
        """Add the bounded native five-terminal GaN/SiC model.

        The thermal node voltage is junction-temperature rise in kelvin. Model
        parameters use the exact public C-structure field names. Backward Euler
        and BDF2 transient runs integrate conservative terminal charge and the
        thermal capacitance; hybrid trapezoidal currently fails closed.
        """

        if not self.library.wbg_fet_electrothermal_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose electrothermal WBG FETs."
            )
        technologies = {"gan_hemt": 0, "sic_mosfet": 1}
        if technology not in technologies:
            raise ValueError("technology must be 'gan_hemt' or 'sic_mosfet'.")
        model = _WbgFetElectrothermalModel()
        code = self.library._library.spikes_wbg_fet_electrothermal_model_init(
            ctypes.byref(model), technologies[technology]
        )
        self.library._check(code, "initializing electrothermal WBG model")
        allowed = {
            name for name, value_type in model._fields_
            if value_type is ctypes.c_double
        }
        unknown = sorted(set(parameters) - allowed)
        if unknown:
            raise ValueError(
                "unknown electrothermal WBG parameter(s): " + ", ".join(unknown)
            )
        for name, value in parameters.items():
            setattr(model, name, _finite(value, name.replace("_", " ")))
        code = self.library._library.spikes_circuit_add_wbg_fet_electrothermal(
            self._open_handle(), _text(element_id, "element id"),
            _text(drain, "drain"), _text(gate, "gate"),
            _text(source, "source"), _text(bulk, "bulk"),
            _text(thermal, "thermal node"), ctypes.byref(model),
        )
        self.library._check(code, f"adding {element_id}")

    def _add_dynamic(
        self, function_name: str, element_id: str, positive: str, negative: str,
        value: float, initial_condition: float,
    ) -> None:
        if not self.library.transient_available:
            raise NativeABIError("Loaded SPIKES ABI-v1 library does not expose transient API v1.")
        code = getattr(self.library._library, function_name)(
            self._open_handle(), _text(element_id, "element id"),
            _text(positive, "positive node"), _text(negative, "negative node"),
            _finite(value, "dynamic element value"),
            _finite(initial_condition, "dynamic element initial condition"),
        )
        self.library._check(code, f"adding {element_id}")

    def add_capacitor(
        self, element_id: str, positive: str, negative: str, capacitance_f: float,
        *, initial_voltage_v: float = 0.0,
    ) -> None:
        self._add_dynamic(
            "spikes_circuit_add_capacitor", element_id, positive, negative,
            capacitance_f, initial_voltage_v,
        )

    def add_inductor(
        self, element_id: str, positive: str, negative: str, inductance_h: float,
        *, initial_current_a: float = 0.0,
    ) -> None:
        self._add_dynamic(
            "spikes_circuit_add_inductor", element_id, positive, negative,
            inductance_h, initial_current_a,
        )

    def add_saturating_inductor(
        self, element_id: str, positive: str, negative: str, *,
        unsaturated_inductance_h: float = 1.0e-3,
        saturated_inductance_h: float = 1.0e-5,
        saturation_current_a: float = 1.0,
        initial_current_a: float = 0.0,
    ) -> None:
        """Add the native smooth flux-linkage saturation DAE."""

        if not self.library.saturating_inductor_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose saturating inductors."
            )
        code = self.library._library.spikes_circuit_add_saturating_inductor(
            self._open_handle(), _text(element_id, "element id"),
            _text(positive, "positive node"),
            _text(negative, "negative node"),
            _finite(unsaturated_inductance_h, "unsaturated inductance"),
            _finite(saturated_inductance_h, "saturated inductance"),
            _finite(saturation_current_a, "saturation current"),
            _finite(initial_current_a, "initial current"),
        )
        self.library._check(code, f"adding {element_id}")

    def solve_operating_point(
        self, *, linear_solver: str = "automatic",
        max_linear_iterations: int = 10_000,
        linear_absolute_tolerance: float = 1.0e-14,
        linear_relative_tolerance: float = 1.0e-10,
        linear_threads: int = 1,
    ) -> "NativeResult":
        methods = {
            "automatic": 0, "dense_lu": 1,
            "conjugate_gradient": 2, "gmres": 3,
            "sparse_lu": 4, "ilu_gmres": 5, "sparse_qr": 6,
        }
        normalized_method = str(linear_solver).strip().lower()
        if normalized_method not in methods:
            raise ValueError(
                "linear_solver must be automatic, dense_lu, conjugate_gradient, "
                "gmres, sparse_lu, ilu_gmres, or sparse_qr."
            )
        for value, label in (
            (max_linear_iterations, "max_linear_iterations"),
            (linear_threads, "linear_threads"),
        ):
            if isinstance(value, bool) or int(value) != value or value <= 0:
                raise ValueError(f"{label} must be a positive integer.")
        result = ctypes.c_void_p()
        solve = self.library._library.spikes_solve_operating_point
        arguments = (self._open_handle(), ctypes.byref(result))
        if self.library.linear_solver_options_available:
            options = _LinearSolverOptions()
            self.library._check(
                self.library._library.spikes_linear_solver_options_init(
                    ctypes.byref(options)
                ),
                "linear solver options initialization",
            )
            options.method = methods[normalized_method]
            options.max_iterations = int(max_linear_iterations)
            options.absolute_tolerance = _finite(
                linear_absolute_tolerance, "linear absolute tolerance"
            )
            options.relative_tolerance = _finite(
                linear_relative_tolerance, "linear relative tolerance"
            )
            options.threads = int(linear_threads)
            solve = self.library._library.spikes_solve_operating_point_with_linear_solver
            arguments = (
                self._open_handle(), ctypes.byref(options), ctypes.byref(result)
            )
        elif normalized_method != "automatic" or linear_threads != 1:
            raise NativeABIError(
                "Loaded SPIKES library does not expose configurable linear solvers."
            )
        self.library._check(
            solve(*arguments),
            "operating-point solve",
        )
        if not result.value:
            raise NativeABIError("operating-point solve returned a null result")
        return NativeResult(self.library, result)

    def solve_transient(
        self, *, time_step_s: float, stop_time_s: float,
        max_steps: int = 1_000_000,
        initialize_from_operating_point: bool = True,
        max_newton_iterations: int = 100,
        max_backtracks: int = 20,
        absolute_tolerance: float = 1.0e-12,
        relative_tolerance: float = 1.0e-9,
        integration_method: str = "backward_euler",
        adaptive_time_step: bool = False,
        minimum_time_step_s: float = 1.0e-15,
        lte_absolute_tolerance: float = 1.0e-6,
        lte_relative_tolerance: float = 1.0e-3,
        max_rejected_steps: int = 10_000,
    ) -> "NativeTransientResult":
        if not self.library.transient_available:
            raise NativeABIError("Loaded SPIKES ABI-v1 library does not expose transient API v1.")
        for value, label in (
            (max_steps, "max_steps"),
            (max_newton_iterations, "max_newton_iterations"),
            (max_backtracks, "max_backtracks"),
        ):
            if isinstance(value, bool) or int(value) != value or value <= 0:
                raise ValueError(f"{label} must be a positive integer.")
        if not isinstance(initialize_from_operating_point, bool):
            raise ValueError("initialize_from_operating_point must be boolean.")
        if not isinstance(adaptive_time_step, bool):
            raise ValueError("adaptive_time_step must be boolean.")
        if isinstance(max_rejected_steps, bool) or int(max_rejected_steps) != max_rejected_steps or max_rejected_steps <= 0:
            raise ValueError("max_rejected_steps must be a positive integer.")
        normalized_method = str(integration_method).strip().lower()
        method_codes = {"backward_euler": 0, "hybrid_trapezoidal": 1, "bdf2": 2}
        if normalized_method not in method_codes:
            raise ValueError(
                "integration_method must be backward_euler, hybrid_trapezoidal, or bdf2."
            )
        if normalized_method == "bdf2" and not self.library.bdf2_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose BDF2 transient integration."
            )
        if normalized_method != "backward_euler" and not self.library.integration_method_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose selectable integration methods."
            )
        if adaptive_time_step and not self.library.adaptive_transient_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose adaptive transient integration."
            )
        options = _TransientOptions()
        self.library._check(
            self.library._library.spikes_transient_options_init(ctypes.byref(options)),
            "transient options initialization",
        )
        if options.struct_version != SPIKES_TRANSIENT_API_VERSION:
            raise NativeABIError(
                f"SPIKES transient API mismatch: expected {SPIKES_TRANSIENT_API_VERSION}, "
                f"received {options.struct_version}."
            )
        options.time_step_s = _finite(time_step_s, "time step")
        options.stop_time_s = _finite(stop_time_s, "stop time")
        options.max_steps = int(max_steps)
        options.initialize_from_operating_point = int(initialize_from_operating_point)
        options.max_newton_iterations = int(max_newton_iterations)
        options.max_backtracks = int(max_backtracks)
        options.absolute_tolerance = _finite(absolute_tolerance, "absolute tolerance")
        options.relative_tolerance = _finite(relative_tolerance, "relative tolerance")
        result = ctypes.c_void_p()
        solve = self.library._library.spikes_solve_transient
        arguments: tuple[Any, ...] = (
            self._open_handle(), ctypes.byref(options), ctypes.byref(result)
        )
        if self.library.integration_method_available:
            solve = self.library._library.spikes_solve_transient_with_method
            arguments = (
                self._open_handle(), ctypes.byref(options),
                method_codes[normalized_method], ctypes.byref(result),
            )
        if adaptive_time_step:
            solve = self.library._library.spikes_solve_transient_adaptive
            arguments = (
                self._open_handle(), ctypes.byref(options),
                method_codes[normalized_method], 1,
                _finite(minimum_time_step_s, "minimum time step"),
                _finite(lte_absolute_tolerance, "LTE absolute tolerance"),
                _finite(lte_relative_tolerance, "LTE relative tolerance"),
                int(max_rejected_steps), ctypes.byref(result),
            )
        self.library._check(
            solve(*arguments),
            "transient solve",
        )
        if not result.value:
            raise NativeABIError("transient solve returned a null result")
        return NativeTransientResult(self.library, result)

    def transient_session(
        self, *, initialize_from_operating_point: bool = False,
        integration_method: str = "backward_euler",
        max_newton_iterations: int = 100, max_backtracks: int = 20,
        absolute_tolerance: float = 1.0e-12,
        relative_tolerance: float = 1.0e-9,
    ) -> "NativeTransientSession":
        """Create an independent persistent BE, hybrid, or BDF2 session snapshot."""

        if not self.library.transient_session_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose persistent transient sessions."
            )
        if not isinstance(initialize_from_operating_point, bool):
            raise ValueError("initialize_from_operating_point must be boolean.")
        normalized_method = str(integration_method).strip().lower()
        method_codes = {"backward_euler": 0, "hybrid_trapezoidal": 1, "bdf2": 2}
        if normalized_method not in method_codes:
            raise ValueError(
                "integration_method must be backward_euler, hybrid_trapezoidal, or bdf2."
            )
        if normalized_method == "bdf2" and not self.library.session_bdf2_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose persistent BDF2 integration."
            )
        if (normalized_method != "backward_euler" and
                not self.library.session_integration_method_available):
            raise NativeABIError(
                "Loaded SPIKES library does not expose method-selecting persistent sessions."
            )
        for value, label in (
            (max_newton_iterations, "max_newton_iterations"),
            (max_backtracks, "max_backtracks"),
        ):
            if isinstance(value, bool) or int(value) != value or value <= 0:
                raise ValueError(f"{label} must be a positive integer.")
        options = _TransientOptions()
        self.library._check(
            self.library._library.spikes_transient_options_init(
                ctypes.byref(options)
            ),
            "persistent transient options initialization",
        )
        options.initialize_from_operating_point = int(initialize_from_operating_point)
        options.max_newton_iterations = int(max_newton_iterations)
        options.max_backtracks = int(max_backtracks)
        options.absolute_tolerance = _finite(absolute_tolerance, "absolute tolerance")
        options.relative_tolerance = _finite(relative_tolerance, "relative tolerance")
        handle = ctypes.c_void_p()
        create = self.library._library.spikes_transient_session_create
        arguments = (
            self._open_handle(), ctypes.byref(options), ctypes.byref(handle)
        )
        if self.library.session_integration_method_available:
            create = self.library._library.spikes_transient_session_create_with_method
            arguments = (
                self._open_handle(), ctypes.byref(options),
                method_codes[normalized_method], ctypes.byref(handle),
            )
        self.library._check(
            create(*arguments),
            "persistent transient session creation",
        )
        if not handle.value:
            raise NativeABIError("persistent transient session returned a null handle")
        return NativeTransientSession(self.library, handle)


class NativeResult:
    """Context-managed immutable native operating-point result."""

    _STATUS = {0: "converged", 1: "singular", 2: "numerical_failure"}

    def __init__(self, library: NativeLibrary, handle: ctypes.c_void_p) -> None:
        self.library = library
        self._handle = handle

    def _open_handle(self) -> ctypes.c_void_p:
        if not self._handle.value:
            raise NativeABIError("native result is closed")
        return self._handle

    def close(self) -> None:
        if self._handle.value:
            self.library._library.spikes_result_destroy(self._handle)
            self._handle = ctypes.c_void_p()

    def __enter__(self) -> "NativeResult":
        self._open_handle()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    @property
    def status(self) -> str:
        code = int(self.library._library.spikes_result_status(self._open_handle()))
        return self._STATUS.get(code, f"unknown:{code}")

    @property
    def message(self) -> str:
        raw = self.library._library.spikes_result_message(self._open_handle())
        return raw.decode("utf-8", errors="replace") if raw else ""

    def _value(self, function_name: str, name: str) -> float:
        output = ctypes.c_double()
        code = getattr(self.library._library, function_name)(
            self._open_handle(), _text(name, "result name"), ctypes.byref(output)
        )
        self.library._check(code, f"querying {name}")
        return float(output.value)

    def node_voltage(self, name: str) -> float:
        return self._value("spikes_result_node_voltage", name)

    def element_current(self, element_id: str) -> float:
        return self._value("spikes_result_element_current", element_id)

    def element_power(self, element_id: str) -> float:
        return self._value("spikes_result_element_power", element_id)

    def diagnostics(self) -> dict[str, float | int]:
        order = ctypes.c_size_t()
        swaps = ctypes.c_size_t()
        residual = ctypes.c_double()
        code = self.library._library.spikes_result_diagnostics(
            self._open_handle(), ctypes.byref(order), ctypes.byref(swaps), ctypes.byref(residual)
        )
        self.library._check(code, "querying diagnostics")
        result = {
            "matrix_order": int(order.value),
            "pivot_swaps": int(swaps.value),
            "residual_inf_norm": float(residual.value),
        }
        if self.library.linear_solver_options_available:
            method = ctypes.c_uint32()
            iterations = ctypes.c_size_t()
            threads = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_result_linear_solver_diagnostics(
                    self._open_handle(), ctypes.byref(method),
                    ctypes.byref(iterations), ctypes.byref(threads),
                ),
                "querying linear solver diagnostics",
            )
            result["linear_solver"] = {
                1: "dense_lu", 2: "conjugate_gradient", 3: "gmres",
                4: "sparse_lu", 5: "ilu_gmres", 6: "sparse_qr",
            }.get(int(method.value), f"unknown:{int(method.value)}")
            result["linear_iterations"] = int(iterations.value)
            result["linear_threads"] = int(threads.value)
        if self.library.sparse_solver_diagnostics_available:
            nonzeros = ctypes.c_size_t()
            symbolic = ctypes.c_size_t()
            numeric = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_result_sparse_solver_diagnostics(
                    self._open_handle(), ctypes.byref(nonzeros),
                    ctypes.byref(symbolic), ctypes.byref(numeric),
                ),
                "querying sparse solver diagnostics",
            )
            result["matrix_nonzeros"] = int(nonzeros.value)
            result["symbolic_analyses"] = int(symbolic.value)
            result["numeric_factorizations"] = int(numeric.value)
        return result


class NativeTransientResult:
    """Context-managed immutable native transient result."""

    _STATUS = NativeResult._STATUS

    def __init__(self, library: NativeLibrary, handle: ctypes.c_void_p) -> None:
        self.library = library
        self._handle = handle

    def _open_handle(self) -> ctypes.c_void_p:
        if not self._handle.value:
            raise NativeABIError("native transient result is closed")
        return self._handle

    def close(self) -> None:
        if self._handle.value:
            self.library._library.spikes_transient_result_destroy(self._handle)
            self._handle = ctypes.c_void_p()

    def __enter__(self) -> "NativeTransientResult":
        self._open_handle()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    @property
    def status(self) -> str:
        code = int(self.library._library.spikes_transient_result_status(self._open_handle()))
        return self._STATUS.get(code, f"unknown:{code}")

    @property
    def message(self) -> str:
        raw = self.library._library.spikes_transient_result_message(self._open_handle())
        return raw.decode("utf-8", errors="replace") if raw else ""

    @property
    def point_count(self) -> int:
        return int(self.library._library.spikes_transient_result_point_count(self._open_handle()))

    def time(self, point_index: int) -> float:
        return self._indexed_value("spikes_transient_result_point_time", point_index)

    def node_voltage(self, point_index: int, name: str) -> float:
        return self._indexed_value("spikes_transient_result_node_voltage", point_index, name)

    def element_current(self, point_index: int, element_id: str) -> float:
        return self._indexed_value("spikes_transient_result_element_current", point_index, element_id)

    def element_power(self, point_index: int, element_id: str) -> float:
        return self._indexed_value("spikes_transient_result_element_power", point_index, element_id)

    def _indexed_value(self, function_name: str, point_index: int, name: str | None = None) -> float:
        if isinstance(point_index, bool) or int(point_index) != point_index or point_index < 0:
            raise ValueError("point index must be a non-negative integer.")
        output = ctypes.c_double()
        function = getattr(self.library._library, function_name)
        arguments: tuple[Any, ...]
        if name is None:
            arguments = (self._open_handle(), int(point_index), ctypes.byref(output))
        else:
            arguments = (
                self._open_handle(), int(point_index), _text(name, "result name"), ctypes.byref(output),
            )
        self.library._check(function(*arguments), f"querying transient point {point_index}")
        return float(output.value)

    def diagnostics(self) -> dict[str, float | int]:
        integer_outputs = [ctypes.c_size_t() for _ in range(5)]
        failed_time = ctypes.c_double()
        residual = ctypes.c_double()
        code = self.library._library.spikes_transient_result_diagnostics(
            self._open_handle(), *(ctypes.byref(item) for item in integer_outputs),
            ctypes.byref(failed_time), ctypes.byref(residual),
        )
        self.library._check(code, "querying transient diagnostics")
        result = dict(zip(
            (
                "matrix_order", "completed_steps", "total_newton_iterations",
                "total_damping_steps", "pivot_swaps",
            ),
            (int(item.value) for item in integer_outputs),
        )) | {
            "failed_time_s": float(failed_time.value),
            "residual_inf_norm": float(residual.value),
        }
        if self.library.breakpoint_diagnostics_available:
            breakpoints = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_transient_result_breakpoint_steps(
                    self._open_handle(), ctypes.byref(breakpoints)
                ),
                "querying transient breakpoint diagnostics",
            )
            result["source_breakpoint_steps"] = int(breakpoints.value)
        if self.library.factorization_diagnostics_available:
            factorizations = ctypes.c_size_t()
            reuses = ctypes.c_size_t()
            entries = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_transient_result_factorization_diagnostics(
                    self._open_handle(), ctypes.byref(factorizations),
                    ctypes.byref(reuses), ctypes.byref(entries),
                ),
                "querying transient factorization diagnostics",
            )
            result.update(
                matrix_factorizations=int(factorizations.value),
                factorization_reuses=int(reuses.value),
                factorization_cache_entries=int(entries.value),
            )
        if self.library.integration_diagnostics_available:
            backward_euler = ctypes.c_size_t()
            trapezoidal = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_transient_result_integration_diagnostics(
                    self._open_handle(), ctypes.byref(backward_euler),
                    ctypes.byref(trapezoidal),
                ),
                "querying transient integration diagnostics",
            )
            result.update(
                backward_euler_steps=int(backward_euler.value),
                trapezoidal_steps=int(trapezoidal.value),
            )
        if self.library.bdf2_available:
            bdf2 = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_transient_result_bdf2_steps(
                    self._open_handle(), ctypes.byref(bdf2)
                ),
                "querying transient BDF2 diagnostics",
            )
            result["bdf2_steps"] = int(bdf2.value)
        if self.library.lte_diagnostics_available:
            rejected = ctypes.c_size_t()
            last_ratio = ctypes.c_double()
            minimum_step = ctypes.c_double()
            maximum_step = ctypes.c_double()
            self.library._check(
                self.library._library.spikes_transient_result_lte_diagnostics(
                    self._open_handle(), ctypes.byref(rejected),
                    ctypes.byref(last_ratio), ctypes.byref(minimum_step),
                    ctypes.byref(maximum_step),
                ),
                "querying transient LTE diagnostics",
            )
            result.update(
                rejected_lte_steps=int(rejected.value),
                last_lte_ratio=float(last_ratio.value),
                minimum_accepted_step_s=float(minimum_step.value),
                maximum_accepted_step_s=float(maximum_step.value),
            )
        if self.library.sparse_lte_diagnostics_available:
            embedded = ctypes.c_size_t()
            assemblies = ctypes.c_size_t()
            symbolic = ctypes.c_size_t()
            numeric = ctypes.c_size_t()
            partial = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_transient_result_sparse_lte_diagnostics(
                    self._open_handle(), ctypes.byref(embedded),
                    ctypes.byref(assemblies), ctypes.byref(symbolic),
                    ctypes.byref(numeric), ctypes.byref(partial),
                ),
                "querying transient sparse/LTE diagnostics",
            )
            result.update(
                embedded_lte_solves=int(embedded.value),
                sparse_assemblies=int(assemblies.value),
                sparse_symbolic_analyses=int(symbolic.value),
                sparse_numeric_factorizations=int(numeric.value),
                partial_numeric_refactorizations=int(partial.value),
            )
        return result


class NativeTransientCheckpoint:
    """Context-managed checkpoint owned by one persistent native session."""

    def __init__(self, library: NativeLibrary, handle: ctypes.c_void_p) -> None:
        self.library = library
        self._handle = handle

    def _open_handle(self) -> ctypes.c_void_p:
        if not self._handle.value:
            raise NativeABIError("native transient checkpoint is closed")
        return self._handle

    def close(self) -> None:
        if self._handle.value:
            self.library._library.spikes_transient_checkpoint_destroy(self._handle)
            self._handle = ctypes.c_void_p()

    def __enter__(self) -> "NativeTransientCheckpoint":
        self._open_handle()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


class NativeTransientSession:
    """Persistent stateful native backward-Euler stepping handle."""

    _STATUS = NativeResult._STATUS

    def __init__(self, library: NativeLibrary, handle: ctypes.c_void_p) -> None:
        self.library = library
        self._handle = handle

    def _open_handle(self) -> ctypes.c_void_p:
        if not self._handle.value:
            raise NativeABIError("native transient session is closed")
        return self._handle

    def close(self) -> None:
        if self._handle.value:
            self.library._library.spikes_transient_session_destroy(self._handle)
            self._handle = ctypes.c_void_p()

    def __enter__(self) -> "NativeTransientSession":
        self._open_handle()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    @property
    def status(self) -> str:
        code = int(
            self.library._library.spikes_transient_session_status(
                self._open_handle()
            )
        )
        return self._STATUS.get(code, f"unknown:{code}")

    @property
    def message(self) -> str:
        raw = self.library._library.spikes_transient_session_message(
            self._open_handle()
        )
        return raw.decode("utf-8", errors="replace") if raw else ""

    def set_source_value(self, element_id: str, value: float) -> None:
        self.library._check(
            self.library._library.spikes_transient_session_set_source_value(
                self._open_handle(), _text(element_id, "source element id"),
                _finite(value, "source value"),
            ),
            f"setting persistent source {element_id}",
        )

    def step(self, step_s: float) -> bool:
        accepted = ctypes.c_uint8()
        self.library._check(
            self.library._library.spikes_transient_session_step(
                self._open_handle(), _finite(step_s, "persistent step"),
                ctypes.byref(accepted),
            ),
            "persistent transient step",
        )
        return bool(accepted.value)

    @property
    def position(self) -> tuple[float, int]:
        time_s = ctypes.c_double()
        step_index = ctypes.c_size_t()
        self.library._check(
            self.library._library.spikes_transient_session_position(
                self._open_handle(), ctypes.byref(time_s), ctypes.byref(step_index)
            ),
            "querying persistent position",
        )
        return float(time_s.value), int(step_index.value)

    @property
    def time_s(self) -> float:
        return self.position[0]

    @property
    def step_index(self) -> int:
        return self.position[1]

    def _value(self, function_name: str, name: str) -> float:
        output = ctypes.c_double()
        self.library._check(
            getattr(self.library._library, function_name)(
                self._open_handle(), _text(name, "persistent result name"),
                ctypes.byref(output),
            ),
            f"querying persistent value {name}",
        )
        return float(output.value)

    def node_voltage(self, name: str) -> float:
        return self._value("spikes_transient_session_node_voltage", name)

    def element_voltage(self, element_id: str) -> float:
        if not self.library.session_element_voltage_available:
            raise NativeABIError(
                "Loaded SPIKES library does not expose persistent element voltage."
            )
        return self._value(
            "spikes_transient_session_element_voltage", element_id
        )

    def element_current(self, element_id: str) -> float:
        return self._value("spikes_transient_session_element_current", element_id)

    def element_power(self, element_id: str) -> float:
        return self._value("spikes_transient_session_element_power", element_id)

    def diagnostics(self) -> dict[str, float | int]:
        completed = ctypes.c_size_t()
        factorizations = ctypes.c_size_t()
        newton = ctypes.c_size_t()
        residual = ctypes.c_double()
        self.library._check(
            self.library._library.spikes_transient_session_diagnostics(
                self._open_handle(), ctypes.byref(completed),
                ctypes.byref(factorizations), ctypes.byref(newton),
                ctypes.byref(residual),
            ),
            "querying persistent diagnostics",
        )
        result = {
            "completed_steps": int(completed.value),
            "matrix_factorizations": int(factorizations.value),
            "total_newton_iterations": int(newton.value),
            "residual_inf_norm": float(residual.value),
        }
        if self.library.session_factorization_diagnostics_available:
            reuses = ctypes.c_size_t()
            cache_entries = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_transient_session_factorization_diagnostics(
                    self._open_handle(), ctypes.byref(reuses),
                    ctypes.byref(cache_entries),
                ),
                "querying persistent factorization diagnostics",
            )
            result["factorization_reuses"] = int(reuses.value)
            result["factorization_cache_entries"] = int(cache_entries.value)
        if self.library.session_integration_diagnostics_available:
            backward_euler = ctypes.c_size_t()
            trapezoidal = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_transient_session_integration_diagnostics(
                    self._open_handle(), ctypes.byref(backward_euler),
                    ctypes.byref(trapezoidal),
                ),
                "querying persistent integration diagnostics",
            )
            result["backward_euler_steps"] = int(backward_euler.value)
            result["trapezoidal_steps"] = int(trapezoidal.value)
        if self.library.session_bdf2_available:
            bdf2 = ctypes.c_size_t()
            self.library._check(
                self.library._library.spikes_transient_session_bdf2_steps(
                    self._open_handle(), ctypes.byref(bdf2)
                ),
                "querying persistent BDF2 diagnostics",
            )
            result["bdf2_steps"] = int(bdf2.value)
        return result

    def checkpoint(self) -> NativeTransientCheckpoint:
        handle = ctypes.c_void_p()
        self.library._check(
            self.library._library.spikes_transient_session_checkpoint_create(
                self._open_handle(), ctypes.byref(handle)
            ),
            "creating persistent checkpoint",
        )
        if not handle.value:
            raise NativeABIError("persistent checkpoint returned a null handle")
        return NativeTransientCheckpoint(self.library, handle)

    def restore(self, checkpoint: NativeTransientCheckpoint) -> None:
        if checkpoint.library is not self.library:
            raise ValueError("checkpoint was loaded from a different native library")
        self.library._check(
            self.library._library.spikes_transient_session_restore(
                self._open_handle(), checkpoint._open_handle()
            ),
            "restoring persistent checkpoint",
        )


def load_native_library(path: str | Path) -> NativeLibrary:
    """Load and verify one explicitly selected local SPIKES shared library."""

    return NativeLibrary(path)


__all__ = [
    "SPIKES_ABI_VERSION", "SPIKES_TRANSIENT_API_VERSION", "NativeABIError",
    "NativeCircuit", "NativeLibrary", "NativeResult", "NativeTransientResult",
    "NativeTransientCheckpoint", "NativeTransientSession",
    "load_native_library",
]
