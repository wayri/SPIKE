# SPDX-License-Identifier: Apache-2.0
"""Fast frozen-package checks for bundled manufacturer approximations."""
from __future__ import annotations


def verify(library, check):
    """Resolve and execute the fixed five-record native approximation tier."""
    from .manufacturer_executable import (
        CONTRACT, MODEL_STATUS, load_catalog, native_recipe, source_pins,
    )
    from .resources import resource_dir
    from python.spikes.native_runner import run_native_project
    from python.spikes.netlist import parse_netlist

    resource = resource_dir("library") / "manufacturer-executable-v1.json"
    check(resource.is_file(), "manufacturer executable catalog JSON bundled")
    catalog = load_catalog()
    check(catalog["contract"] == CONTRACT, "bundled manufacturer executable catalog resolves")
    expected = {
        "ti-lm358", "adi-ad620", "onsemi-mmbt3904lt1g",
        "onsemi-2n7002l", "nexperia-bas316",
    }
    check({row["discovery_id"] for row in catalog["records"]} == expected,
          "bundled manufacturer executable tier retains exactly five reviewed identities")
    check(all(row["model_status"] == MODEL_STATUS and row["qualified"] is False
              for row in catalog["records"]),
          "bundled manufacturer executable tier remains explicitly unqualified")
    check(len(source_pins("ti-lm358")) == 8 and len(source_pins("adi-ad620")) == 8,
          "bundled amplifier approximations retain full eight-pin package context")

    fixtures = {
        "ti-lm358": (
            "VCC vp 0 5\nVINA ina 0 .5\nVINB inb 0 2\n"
            "X1 outa outa ina 0 inb outb outb vp @MODEL@\nRLA outa 0 10k\nRLB outb 0 10k",
            "node_voltage_v", "outa", 0.5, 20e-6,
        ),
        "adi-ad620": (
            "VP vp 0 5\nVM vm 0 -5\nVIP ip 0 .05\nVIM im 0 -.05\nVREF ref 0 0\n"
            "X1 rg1 im ip vm ref out vp rg2 @MODEL@\nRG rg1 rg2 5488.888888888889\nRLOAD out 0 10k",
            "node_voltage_v", "out", 1.0, 2e-4,
        ),
        "onsemi-mmbt3904lt1g": (
            "VCC vp 0 5\nVB b 0 .7\nRC vp c 1k\nX1 b 0 c @MODEL@",
            "element_current_a", "X1:QCORE", 2.999499877e-5, 2e-12,
        ),
        "onsemi-2n7002l": (
            "VDD vp 0 5\nVG g 0 3\nRD vp d 100\nX1 g 0 d @MODEL@",
            "element_current_a", "X1:MCORE", 0.0125, 1e-10,
        ),
        "nexperia-bas316": (
            "VD a 0 .715\nX1 0 a @MODEL@",
            "element_current_a", "X1:DCORE", 0.001, 1e-8,
        ),
    }
    for row in catalog["records"]:
        identity = row["discovery_id"]
        recipe = native_recipe(row)
        body, section, signal, expected_value, tolerance = fixtures[identity]
        deck = recipe["source"] + body.replace("@MODEL@", recipe["name"]) + "\n.op\n.end\n"
        project = parse_netlist(deck, native_extensions=True)
        check(bool(project.elements), identity + " packaged native recipe parses")
        result = run_native_project(project, str(library)).to_dict()
        check(result["status"] == "completed", identity + " packaged native recipe executes")
        actual = result["data"][section][signal]
        check(abs(actual - expected_value) <= tolerance,
              identity + " packaged native result matches bounded oracle")


__all__ = ["verify"]
