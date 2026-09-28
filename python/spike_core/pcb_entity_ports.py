# SPDX-License-Identifier: Apache-2.0
"""Compatibility import for OpenEMS extension entity ports."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("extensions.openems_suite.pcb_entity_ports")
