# SPDX-License-Identifier: Apache-2.0
"""Generate an owned native DigitalKernel portfolio regression source.

This is a build-time reference generator, not a shipped Python logic runtime.
It translates the canonical executable package descriptors into typed C++ SDK
primitive graphs and independently derives bounded truth/stimulus vectors.  It
does not compile, run, download, import, or execute vendor material.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spikes.logic_portfolio import catalog  # noqa: E402


CONTRACT = "spikes/logic-native-test-corpus/v1"
CANONICAL_MODELS = (
    "HC00", "HC02", "HC04", "HC08", "HC10", "HC11", "HC20", "HC21", "HC32", "HC86",
    "HC125", "HC126", "HC138", "HC139", "HC151", "HC153", "HC157", "HC283", "HC688", "HC245",
)
KIND = {
    "buf": "PrimitiveKind::buffer", "not": "PrimitiveKind::invert",
    "and": "PrimitiveKind::and_gate", "or": "PrimitiveKind::or_gate",
    "xor": "PrimitiveKind::xor_gate", "nand": "PrimitiveKind::nand_gate",
    "nor": "PrimitiveKind::nor_gate", "tristate": "PrimitiveKind::tristate",
    "dff": "PrimitiveKind::dff",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bits(value: int, width: int, prefix: str, *, first: int = 0) -> dict[str, int]:
    return {f"{prefix}{index + first}": (value >> index) & 1 for index in range(width)}


def _gate_vectors(model_id: str, descriptor: dict) -> list[dict]:
    operations: dict[str, Callable[[tuple[int, ...]], int]] = {
        "HC00": lambda values: int(not all(values)), "HC02": lambda values: int(not any(values)),
        "HC04": lambda values: int(not values[0]), "HC08": lambda values: int(all(values)),
        "HC10": lambda values: int(not all(values)), "HC11": lambda values: int(all(values)),
        "HC20": lambda values: int(not all(values)), "HC21": lambda values: int(all(values)),
        "HC32": lambda values: int(any(values)), "HC86": lambda values: sum(values) % 2,
    }
    primitives = descriptor["primitives"]
    vectors = []
    for values in itertools.product((0, 1), repeat=len(primitives[0]["inputs"])):
        inputs: dict[str, int] = {}
        expected: dict[str, int] = {}
        for primitive in primitives:
            inputs.update(zip(primitive["inputs"], values))
            expected[primitive["output"]] = operations[model_id](values)
        vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _tristate_vectors(model_id: str) -> list[dict]:
    enabled_level = 0 if model_id == "HC125" else 1
    vectors = []
    for data, enabled in itertools.product((0, 1), repeat=2):
        inputs = {}
        expected = {}
        for channel in range(1, 5):
            inputs[f"{channel}A"] = data
            inputs[f"{channel}OE"] = enabled_level if enabled else 1 - enabled_level
            expected[f"{channel}Y"] = data if enabled else "z"
        vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _decoder138_vectors() -> list[dict]:
    vectors = []
    for address in range(8):
        for g1, g2a, g2b in itertools.product((0, 1), repeat=3):
            enabled = g1 == 1 and g2a == 0 and g2b == 0
            inputs = {"A": address & 1, "B": (address >> 1) & 1,
                      "C": (address >> 2) & 1, "G1": g1, "G2A": g2a, "G2B": g2b}
            expected = {f"Y{index}": int(not (enabled and index == address)) for index in range(8)}
            vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _decoder139_vectors() -> list[dict]:
    vectors = []
    for packed in range(64):
        inputs = {
            "1G": packed & 1, "1A": (packed >> 1) & 1, "1B": (packed >> 2) & 1,
            "2G": (packed >> 3) & 1, "2A": (packed >> 4) & 1, "2B": (packed >> 5) & 1,
        }
        expected = {}
        for channel in (1, 2):
            address = inputs[f"{channel}A"] | (inputs[f"{channel}B"] << 1)
            enabled = inputs[f"{channel}G"] == 0
            expected.update({f"{channel}Y{index}": int(not (enabled and index == address))
                             for index in range(4)})
        vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _mux151_vectors() -> list[dict]:
    vectors = []
    for pattern in (0x00, 0xFF, 0xA5, 0x3C):
        for selected in range(8):
            for disabled in (0, 1):
                inputs = _bits(pattern, 8, "I")
                inputs.update({"S0": selected & 1, "S1": (selected >> 1) & 1,
                               "S2": (selected >> 2) & 1, "E": disabled})
                y = 0 if disabled else inputs[f"I{selected}"]
                vectors.append({"inputs": inputs, "expected": {"Y": y, "Y_N": 1 - y}})
    return vectors


def _mux153_vectors() -> list[dict]:
    vectors = []
    patterns = ((0x0, 0xF), (0x5, 0xA), (0x3, 0xC), (0x9, 0x6))
    for first, second in patterns:
        for selected in range(4):
            for g1, g2 in itertools.product((0, 1), repeat=2):
                inputs = {"S0": selected & 1, "S1": (selected >> 1) & 1, "1G": g1, "2G": g2}
                inputs.update({f"1I{i}": (first >> i) & 1 for i in range(4)})
                inputs.update({f"2I{i}": (second >> i) & 1 for i in range(4)})
                expected = {"1Y": 0 if g1 else inputs[f"1I{selected}"],
                            "2Y": 0 if g2 else inputs[f"2I{selected}"]}
                vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _mux157_vectors() -> list[dict]:
    vectors = []
    patterns = ((0x0, 0xF), (0x5, 0xA), (0x3, 0xC), (0x9, 0x6))
    for first, second in patterns:
        for select, disabled in itertools.product((0, 1), repeat=2):
            inputs = {"S": select, "G": disabled}
            for channel in range(1, 5):
                inputs[f"{channel}A"] = (first >> (channel - 1)) & 1
                inputs[f"{channel}B"] = (second >> (channel - 1)) & 1
            expected = {f"{channel}Y": 0 if disabled else inputs[f"{channel}{'B' if select else 'A'}"]
                        for channel in range(1, 5)}
            vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _adder283_vectors() -> list[dict]:
    vectors = []
    for a, b, carry in itertools.product(range(16), range(16), (0, 1)):
        inputs = _bits(a, 4, "A", first=1)
        inputs.update(_bits(b, 4, "B", first=1))
        inputs["CIN"] = carry
        total = a + b + carry
        expected = _bits(total, 4, "S", first=1)
        expected["COUT"] = (total >> 4) & 1
        vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _comparator688_vectors() -> list[dict]:
    pairs = [(value, value) for value in (0x00, 0x55, 0xAA, 0xFF)]
    pairs.extend((0xA5, 0xA5 ^ (1 << bit)) for bit in range(8))
    vectors = []
    for p, q in pairs:
        for disabled in (0, 1):
            inputs = {"G": disabled, **_bits(p, 8, "P"), **_bits(q, 8, "Q")}
            expected = {"P_EQ_Q_N": int(disabled or p != q)}
            vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _transceiver245_vectors() -> list[dict]:
    vectors = []
    for pattern in (0x00, 0xFF, 0xA5, 0x5A):
        for direction, disabled in itertools.product((0, 1), repeat=2):
            source, target = ("A", "B") if direction else ("B", "A")
            inputs = {"DIR": direction, "OE": disabled}
            inputs.update(_bits(pattern, 8, source, first=1))
            expected = {f"{target}{index}": "z" if disabled else (pattern >> (index - 1)) & 1
                        for index in range(1, 9)}
            vectors.append({"inputs": inputs, "expected": expected})
    return vectors


def _vectors(model_id: str, descriptor: dict) -> list[dict]:
    if model_id in CANONICAL_MODELS[:10]:
        return _gate_vectors(model_id, descriptor)
    if model_id in {"HC125", "HC126"}:
        return _tristate_vectors(model_id)
    return {
        "HC138": _decoder138_vectors, "HC139": _decoder139_vectors,
        "HC151": _mux151_vectors, "HC153": _mux153_vectors,
        "HC157": _mux157_vectors, "HC283": _adder283_vectors,
        "HC688": _comparator688_vectors, "HC245": _transceiver245_vectors,
    }[model_id]()


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _logic(value: int | str) -> str:
    return {0: "LogicValue::zero", 1: "LogicValue::one", "z": "LogicValue::z"}[value]


def _pairs(values: dict[str, int | str], endpoints: dict[str, str]) -> str:
    return "{" + ", ".join("{" + _q(endpoints[name]) + ", " + _logic(value) + "}"
                             for name, value in values.items()) + "}"


def _model_cpp(descriptor: dict, vectors: list[dict]) -> str:
    pin_endpoint: dict[str, str] = {}
    signals = []
    for pin in descriptor["pins"]:
        endpoint = f"pin{pin['number']}"
        signals.append(endpoint)
        # Duplicate NC names are intentionally irrelevant to every primitive.
        if pin["name"] not in pin_endpoint:
            pin_endpoint[pin["name"]] = endpoint
    internal_endpoint = {name: f"internal{index}" for index, name in enumerate(descriptor["internal_signals"], 1)}
    endpoints = {**pin_endpoint, **internal_endpoint}
    signals.extend(internal_endpoint.values())
    primitive_lines = []
    for index, primitive in enumerate(descriptor["primitives"], 1):
        inputs = "{" + ", ".join(_q(endpoints[name]) for name in primitive["inputs"]) + "}"
        primitive_lines.append("{" + ", ".join((
            _q(f"p{index}"), KIND[primitive["kind"]], inputs, _q(endpoints[primitive["output"]]), "0")) + "}")
    vector_lines = ["{" + _pairs(vector["inputs"], endpoints) + ", "
                    + _pairs(vector["expected"], endpoints) + "}" for vector in vectors]
    return "ModelSpec{" + ",\n".join((
        _q(descriptor["model_id"]),
        "{" + ", ".join(_q(signal) for signal in signals) + "}",
        "{\n      " + ",\n      ".join(primitive_lines) + "\n    }",
        "{\n      " + ",\n      ".join(vector_lines) + "\n    }",
    )) + "}"


def _cpp_source(models: list[tuple[dict, list[dict]]]) -> str:
    rendered = ",\n    ".join(_model_cpp(descriptor, vectors) for descriptor, vectors in models)
    return f'''// SPDX-License-Identifier: Apache-2.0
// Generated by scripts/build_spikes_logic_native_test.py; do not edit.
// Original SPIKE test vectors; manufacturer sources supplied function/pin facts only.
#include "spikes/digital_kernel.hpp"

#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using spikes::digital::DigitalKernel;
using spikes::digital::LogicValue;
using spikes::digital::PrimitiveDescriptor;
using spikes::digital::PrimitiveKind;
using spikes::digital::SignalDescriptor;

struct TestVector {{
  std::vector<std::pair<std::string, LogicValue>> inputs;
  std::vector<std::pair<std::string, LogicValue>> expected;
}};
struct ModelSpec {{
  std::string id;
  std::vector<std::string> signals;
  std::vector<PrimitiveDescriptor> primitives;
  std::vector<TestVector> vectors;
}};

static std::vector<ModelSpec> corpus() {{
  return {{
    {rendered}
  }};
}}

int main() {{
  std::size_t checked = 0;
  try {{
    for (const auto& model : corpus()) {{
      for (const auto& vector : model.vectors) {{
        DigitalKernel kernel;
        for (const auto& signal : model.signals)
          kernel.add_signal(SignalDescriptor{{signal, LogicValue::z}});
        for (const auto& primitive : model.primitives) kernel.add_primitive(primitive);
        for (const auto& [signal, value] : vector.inputs)
          kernel.drive(signal, "stim_" + signal, value, 0);
        kernel.run_until(0);
        for (const auto& [signal, expected] : vector.expected) {{
          if (kernel.value(signal) != expected)
            throw std::runtime_error("logic portfolio mismatch: " + model.id + " signal " + signal);
        }}
        ++checked;
      }}
    }}
  }} catch (const std::exception& error) {{
    std::cerr << error.what() << '\\n';
    return 1;
  }}
  std::cout << "SPIKE native logic portfolio passed " << checked << " vectors\\n";
  return 0;
}}
'''


def _cmake_source() -> str:
    include_dir = (ROOT / "src").as_posix().replace('"', '\\"')
    return f'''# Generated by scripts/build_spikes_logic_native_test.py; do not edit.
cmake_minimum_required(VERSION 3.20)
project(spikes_logic_portfolio_native_test LANGUAGES CXX)
add_executable(spikes_logic_portfolio_native_test logic_portfolio_native_test.cpp)
target_compile_features(spikes_logic_portfolio_native_test PRIVATE cxx_std_20)
target_include_directories(spikes_logic_portfolio_native_test PRIVATE "{include_dir}")
if(MSVC)
  target_compile_options(spikes_logic_portfolio_native_test PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(spikes_logic_portfolio_native_test PRIVATE -Wall -Wextra -Werror)
endif()
'''


def build(output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    descriptors = {item["model_id"]: item for item in catalog(include_review_only=False)
                   if item["device_family"] != "generic core"}
    if set(descriptors) != set(CANONICAL_MODELS) or len(descriptors) != 20:
        raise ValueError("canonical executable portfolio drifted; review generator and vectors")
    models = []
    for model_id in CANONICAL_MODELS:
        descriptor = descriptors[model_id]
        if descriptor["support"] != "executable" or descriptor["model_status"] != "generic_functional_unqualified":
            raise ValueError(f"{model_id} is not an admitted executable generic functional descriptor")
        models.append((descriptor, _vectors(model_id, descriptor)))
    output_dir.mkdir(parents=True, exist_ok=False)
    source_path = output_dir / "logic_portfolio_native_test.cpp"
    source_path.write_text(_cpp_source(models), encoding="ascii", newline="\n")
    cmake_path = output_dir / "CMakeLists.txt"
    cmake_path.write_text(_cmake_source(), encoding="ascii", newline="\n")
    manifest = {
        "contract": CONTRACT,
        "status": "generated_not_executed",
        "native_header": "src/spikes/digital_kernel.hpp",
        "models": [{"model_id": descriptor["model_id"], "vectors": len(vectors)}
                   for descriptor, vectors in models],
        "distinct_models": len(models),
        "total_vectors": sum(len(vectors) for _, vectors in models),
        "source_sha256": _sha256(source_path),
        "cmake_sha256": _sha256(cmake_path),
        "inputs_sha256": {
            "logic_portfolio.py": _sha256(ROOT / "python/spikes/logic_portfolio.py"),
            "digital_kernel.hpp": _sha256(ROOT / "src/spikes/digital_kernel.hpp"),
        },
        "limitations": [
            "Generated source has not been compiled or executed by this script.",
            "Vectors validate four-state functional composition, not electrical or timing behavior.",
            "Package/orderable aliases and review-only exact sequential families are excluded.",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="ascii")
    return {"source": str(source_path), "cmake": str(cmake_path), "manifest": str(manifest_path),
            "distinct_models": len(models), "total_vectors": manifest["total_vectors"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="fresh directory for generated C++ source and manifest")
    result = build(parser.parse_args().output_dir.resolve())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
