"""
SPIKE Python Bindings Test
===========================

Version: 0.2.0-alpha.2

This script tests the Python bindings for the C++ PEEC solver.

Usage:
    python test_bindings.py
"""

import sys
from pathlib import Path

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent / "python"))

try:
    import spike_core as spike_api
    import spike_peec_native as spike_core
    print("SUCCESS: spike_peec_native module imported successfully!")
except ImportError as e:
    print(f"FAILED: Failed to import the SPIKE API or native PEEC binding: {e}")
    sys.exit(1)

print(f"\nSPIKE Core Version: {spike_api.__version__}")

# Test 1: Create a simple filament
print("\n" + "="*70)
print("Test 1: Create and display a filament")
print("="*70)

fil = spike_core.Filament()
fil.start = spike_core.Point3D(0, 0, 0)
fil.end = spike_core.Point3D(10, 0, 0)
fil.width = 0.5
fil.thickness = 0.035

print(f"Filament: {fil}")
print(f"Length: {fil.length():.2f} mm")

# Test 2: PEEC Solver
print("\n" + "="*70)
print("Test 2: PEEC Solver")
print("="*70)

solver = spike_core.PEECSolver()
solver.add_filament(fil)
print(f"Solver has {solver.num_filaments()} filaments")

L = solver.compute_partial_inductance()
print(f"L matrix shape: {L.shape}")
print(f"Self-inductance: {L[0,0]*1e9:.2f} nH")

# Test 3: Multiple filaments
print("\n" + "="*70)
print("Test 3: Coupled traces")
print("="*70)

solver2 = spike_core.PEECSolver()

# Trace 1
fil1 = spike_core.Filament()
fil1.start = spike_core.Point3D(0, 0, 0)
fil1.end = spike_core.Point3D(10, 0, 0)
fil1.width = 0.5
fil1.thickness = 0.035

# Trace 2
fil2 = spike_core.Filament()
fil2.start = spike_core.Point3D(0, 2, 0)
fil2.end = spike_core.Point3D(10, 2, 0)
fil2.width = 0.5
fil2.thickness = 0.035

solver2.add_filament(fil1)
solver2.add_filament(fil2)

L2 = solver2.compute_partial_inductance()
print(f"L Matrix:\n{L2}")

print("\n" + "="*70)
print("All tests completed successfully!")
print("="*70)
