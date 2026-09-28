"""
SPIKE - Python Module Import Test
===========================================

Tests that Python modules can be imported correctly.
No external dependencies required.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Test all Python module imports"""
    
    print("\n" + "="*70)
    print(" SPIKE - Python Module Import Test".center(70))
    print("="*70 + "\n")
    
    tests_passed = 0
    tests_total = 0
    
    # Test main package
    tests_total += 1
    try:
        import python
        print(f"[OK] python package imported (version: {python.__version__})")
        tests_passed += 1
    except Exception as e:
        print(f"[FAIL] python package: {e}")
    
    # Test GUI subpackage
    tests_total += 1
    try:
        import python.gui
        print(f"[OK] python.gui subpackage imported (version: {python.gui.__version__})")
        tests_passed += 1
    except Exception as e:
        print(f"[FAIL] python.gui: {e}")
    
    # Test viz subpackage
    tests_total += 1
    try:
        import python.viz
        print(f"[OK] python.viz subpackage imported (version: {python.viz.__version__})")
        tests_passed += 1
    except Exception as e:
        print(f"[FAIL] python.viz: {e}")
    
    # Test io subpackage
    tests_total += 1
    try:
        import python.io
        print(f"[OK] python.io subpackage imported (version: {python.io.__version__})")
        tests_passed += 1
    except Exception as e:
        print(f"[FAIL] python.io: {e}")
    
    # Summary
    print("\n" + "="*70)
    print(f" Summary: {tests_passed}/{tests_total} tests passed ".center(70))
    print("="*70 + "\n")
    
    if tests_passed == tests_total:
        print("[SUCCESS] All Python modules can be imported correctly!")
        print("SPIKE Python package structure is valid.\n")
        return 0
    else:
        print(f"[WARNING] {tests_total - tests_passed} import test(s) failed.\n")
        return 1

if __name__ == "__main__":
    sys.exit(test_imports())
