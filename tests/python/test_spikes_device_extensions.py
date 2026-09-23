import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError

from python.spikes.device_contracts import (
    DEVICE_CONTRACT,
    DEVICE_EXTENSION_CONTRACT,
    BehavioralFlags,
    DeviceDescriptor,
    DeviceExtensionManifest,
    DeviceValidityEnvelope,
    DeviceVariable,
    ElectricalTerminal,
    PowerPort,
    RuntimeProvenance,
    SolverInterface,
    ValidityBound,
)
from python.spikes.device_extensions import (
    DeviceExtensionError,
    DeviceExtensionRegistry,
    PolynomialIVDevice,
    RegistryLimits,
    TableIVDevice,
)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def provenance(kind="declarative", trust="untrusted", reviewer=""):
    return RuntimeProvenance(
        implementation_kind=kind,
        implementation_id="fixture/four-quadrant/v1",
        sha256=sha("immutable fixture"),
        trust=trust,
        reviewed_by=reviewer,
        build_id="test-build-1",
    )


def descriptor(runtime=None, power_ports=()):
    runtime = runtime or provenance()
    coupled = tuple(f"{port.domain}_coupling" for port in power_ports)
    return DeviceDescriptor(
        device_id="reference.four_quadrant",
        title="Signed four-quadrant reference",
        electrical_terminals=(ElectricalTerminal("p"), ElectricalTerminal("n", reference=True)),
        power_ports=power_ports,
        variables=(
            DeviceVariable("scale", "parameter", "1", 1.0, 0.0, 10.0),
            DeviceVariable("charge", "state", "C", 0.0),
            DeviceVariable("current", "observable", "A", 0.0),
            DeviceVariable("absorbed_power", "observable", "W", 0.0),
        ),
        validity=DeviceValidityEnvelope((
            ValidityBound("voltage", "V", -2.0, 2.0),
            ValidityBound("temperature", "K", 200.0, 500.0),
        )),
        solver=SolverInterface(
            capabilities=(
                "dc_residual", "analytic_jacobian", "four_quadrant_iv",
                "negative_differential_resistance", *coupled,
            ),
            residual_form="explicit_current",
            jacobian="analytic",
        ),
        behavior=BehavioralFlags(
            four_quadrant=True, ndr_allowed=True, passive=False, reciprocal=False
        ),
        runtime=runtime,
    )


def manifest(runtime=None):
    runtime = runtime or provenance()
    return DeviceExtensionManifest(
        extension_id="reference.devices",
        version="1.0.0",
        api_version=1,
        device_ids=("reference.four_quadrant",),
        required_host_capabilities=(
            "dc_residual", "analytic_jacobian", "four_quadrant_iv",
            "negative_differential_resistance",
        ),
        provenance=runtime,
    )


class DeviceExtensionContractTests(unittest.TestCase):
    def test_typed_physical_ports_have_power_conjugate_quantities(self):
        ports = tuple(PowerPort(f"{domain}_port", domain) for domain in (
            "thermal", "rotational", "translational", "magnetic", "acoustic"
        ))
        device = descriptor(power_ports=ports)
        encoded = device.to_dict()
        self.assertEqual(encoded["contract"], DEVICE_CONTRACT)
        self.assertEqual(encoded["power_ports"][0]["effort"], {"name": "temperature", "unit": "K"})
        self.assertEqual(encoded["power_ports"][1]["flow"], {"name": "torque", "unit": "N*m"})
        self.assertEqual(encoded["power_ports"][4]["flow"]["unit"], "m^3/s")
        json.dumps(encoded, allow_nan=False, sort_keys=True)

    def test_contracts_are_immutable_and_flags_do_not_force_passivity(self):
        device = descriptor()
        self.assertFalse(device.behavior.passive)
        self.assertFalse(device.behavior.reciprocal)
        self.assertTrue(device.behavior.four_quadrant)
        self.assertTrue(device.behavior.ndr_allowed)
        with self.assertRaises(FrozenInstanceError):
            device.title = "tampered"

    def test_descriptor_rejects_undeclared_coupling_and_behavior(self):
        with self.assertRaisesRegex(ValueError, "thermal_coupling"):
            DeviceDescriptor(
                device_id="bad.thermal", title="bad",
                electrical_terminals=(ElectricalTerminal("p"),),
                power_ports=(PowerPort("case", "thermal"),),
                variables=(DeviceVariable("current", "observable", "A"),),
                validity=DeviceValidityEnvelope((ValidityBound("voltage", "V", -1, 1),)),
                solver=SolverInterface(("dc_residual",), "explicit_current", "none"),
                behavior=BehavioralFlags(), runtime=provenance(),
            )
        with self.assertRaisesRegex(ValueError, "four_quadrant_iv"):
            DeviceDescriptor(
                device_id="bad.quadrant", title="bad",
                electrical_terminals=(ElectricalTerminal("p"),), power_ports=(),
                variables=(DeviceVariable("current", "observable", "A"),),
                validity=DeviceValidityEnvelope((ValidityBound("voltage", "V", -1, 1),)),
                solver=SolverInterface(("dc_residual",), "explicit_current", "none"),
                behavior=BehavioralFlags(four_quadrant=True), runtime=provenance(),
            )

    def test_extension_contract_fails_closed_for_execution_or_unknown_capability(self):
        with self.assertRaisesRegex(ValueError, "not implemented"):
            DeviceExtensionManifest(
                "unsafe", "1.0.0", 1, ("reference.four_quadrant",), (), provenance(),
                execution_enabled=True,
            )
        with self.assertRaisesRegex(ValueError, "Unsupported solver capabilities"):
            SolverInterface(("quantum_magic",), "implicit_residual", "analytic")

    def test_untrusted_native_registration_is_forbidden(self):
        native = provenance("native", "untrusted")
        registry = DeviceExtensionRegistry({
            "dc_residual", "analytic_jacobian", "four_quadrant_iv",
            "negative_differential_resistance",
        })
        with self.assertRaisesRegex(DeviceExtensionError, "Untrusted native"):
            registry.register(manifest(native), (descriptor(native),))

    def test_bounded_registration_validates_host_and_exact_device_set(self):
        capabilities = {
            "dc_residual", "analytic_jacobian", "four_quadrant_iv",
            "negative_differential_resistance",
        }
        registry = DeviceExtensionRegistry(capabilities)
        registry.register(manifest(), (descriptor(),))
        self.assertEqual(tuple(registry.devices), ("reference.four_quadrant",))
        self.assertEqual(registry.extensions["reference.devices"].contract, DEVICE_EXTENSION_CONTRACT)
        with self.assertRaises(TypeError):
            registry.devices["new"] = descriptor()
        tiny = DeviceExtensionRegistry(capabilities, RegistryLimits(max_ports_per_device=1))
        with self.assertRaisesRegex(DeviceExtensionError, "port limit"):
            tiny.register(manifest(), (descriptor(),))
        deficient = DeviceExtensionRegistry({"dc_residual"})
        with self.assertRaisesRegex(DeviceExtensionError, "Host lacks"):
            deficient.register(manifest(), (descriptor(),))

    def test_signed_table_supports_all_quadrants_ndr_and_power_direction(self):
        # Each segment is legal; the curve is intentionally active and contains NDR.
        table = TableIVDevice((
            (-2.0, -2.0), (-1.0, 1.0), (1.0, -1.0), (2.0, 2.0)
        ), ndr_allowed=True)
        cases = ((-2.0, "III", 4.0), (-1.0, "II", -1.0),
                 (1.0, "IV", -1.0), (2.0, "I", 4.0))
        for voltage, quadrant, power in cases:
            result = table.evaluate(voltage)
            self.assertEqual(result.quadrant, quadrant)
            self.assertAlmostEqual(result.absorbed_power_w, power)
        self.assertLess(table.evaluate(0.0).conductance_s, 0.0)
        with self.assertRaisesRegex(DeviceExtensionError, "explicitly allowed"):
            TableIVDevice(((-1.0, 1.0), (1.0, -1.0)), ndr_allowed=False)
        with self.assertRaisesRegex(DeviceExtensionError, "validity range"):
            table.evaluate(3.0)

    def test_analytic_four_quadrant_reference_has_exact_jacobian(self):
        # I = v^3 - v: QII/QIV near zero, QI/QIII at larger magnitude.
        device = PolynomialIVDevice((0.0, -1.0, 0.0, 1.0), (-2.0, 2.0), ndr_allowed=True)
        expected = ((-2.0, "III"), (-0.5, "II"), (0.5, "IV"), (2.0, "I"))
        for voltage, quadrant in expected:
            self.assertEqual(device.evaluate(voltage).quadrant, quadrant)
        at_half = device.evaluate(0.5)
        self.assertAlmostEqual(at_half.current_a, -0.375)
        self.assertAlmostEqual(at_half.conductance_s, -0.25)
        self.assertAlmostEqual(at_half.absorbed_power_w, -0.1875)
        with self.assertRaisesRegex(DeviceExtensionError, "explicitly allowed"):
            PolynomialIVDevice((0.0, -1.0), (-1.0, 1.0), ndr_allowed=False)


if __name__ == "__main__":
    unittest.main()
