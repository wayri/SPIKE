"""
SPIKE - Project Structure Validation Test
===================================================

This script validates that all required files and directories exist.
No external dependencies required - uses only Python standard library.
"""

import os
import sys
from pathlib import Path

# ANSI colors (will work in most terminals)
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header(msg):
    print(f"\n{BLUE}{BOLD}{'='*70}{RESET}")
    print(f"{BLUE}{BOLD}{msg:^70}{RESET}")
    print(f"{BLUE}{BOLD}{'='*70}{RESET}\n")

def check_file(path, description):
    """Check if a file exists"""
    if path.exists() and path.is_file():
        size = path.stat().st_size
        print(f"{GREEN}[OK]{RESET} {description:50} ({size:,} bytes)")
        return True
    else:
        print(f"{RED}[MISSING]{RESET} {description}")
        return False

def check_dir(path, description):
    """Check if a directory exists"""
    if path.exists() and path.is_dir():
        # Count files in directory
        file_count = len(list(path.rglob('*')))
        print(f"{GREEN}[OK]{RESET} {description:50} ({file_count} items)")
        return True
    else:
        print(f"{RED}[MISSING]{RESET} {description}")
        return False

def main():
    print_header("SPIKE - Project Structure Validation")
    
    # Get project root
    project_root = Path(__file__).parent
    print(f"Project Root: {project_root}\n")
    
    total_checks = 0
    passed_checks = 0
    
    # Documentation files
    print(f"{BOLD}Documentation Files:{RESET}")
    docs = [
        ("README.md", "Project README"),
        ("ARCHITECTURE.md", "Architecture documentation"),
        ("DEVELOPMENT.md", "Development guide"),
        ("RELEASE_NOTES.md", "Release notes"),
        ("codex_migration/DONE.md", "Current completion tracker"),
    ]
    for filename, desc in docs:
        total_checks += 1
        if check_file(project_root / filename, desc):
            passed_checks += 1
    
    # Build system
    print(f"\n{BOLD}Build System:{RESET}")
    build_files = [
        ("CMakeLists.txt", "CMake configuration"),
        (".gitignore", "Git ignore file"),
    ]
    for filename, desc in build_files:
        total_checks += 1
        if check_file(project_root / filename, desc):
            passed_checks += 1
    
    # Infrastructure
    print(f"\n{BOLD}Infrastructure:{RESET}")
    infra_files = [
        ("ccd_tracker.json", "Session state tracker"),
        ("infra/aether_boot.py", "Environment bootstrap"),
    ]
    for filename, desc in infra_files:
        total_checks += 1
        if check_file(project_root / filename, desc):
            passed_checks += 1
    
    # C++ Kernel
    print(f"\n{BOLD}C++ Kernel:{RESET}")
    cpp_files = [
        ("src/peec/peec_solver.hpp", "PEEC solver header"),
        ("src/peec/peec_solver.cpp", "PEEC solver implementation"),
        ("src/thermal/thermal_solver.hpp", "Thermal solver header"),
        ("src/thermal/thermal_solver.cpp", "Thermal solver implementation"),
        ("src/math/sparse_solver.hpp", "Math utilities header"),
    ]
    for filename, desc in cpp_files:
        total_checks += 1
        if check_file(project_root / filename, desc):
            passed_checks += 1
    
    # Python Shell
    print(f"\n{BOLD}Python Shell:{RESET}")
    python_files = [
        ("python/__init__.py", "Python package init"),
        ("python/gui/__init__.py", "GUI subpackage init"),
        ("python/gui/main.py", "Main GUI application"),
        ("python/viz/__init__.py", "Visualization subpackage init"),
        ("python/io/__init__.py", "I/O subpackage init"),
    ]
    for filename, desc in python_files:
        total_checks += 1
        if check_file(project_root / filename, desc):
            passed_checks += 1
    
    # Directories
    print(f"\n{BOLD}Directory Structure:{RESET}")
    directories = [
        ("src", "C++ source directory"),
        ("src/peec", "PEEC solver directory"),
        ("src/thermal", "Thermal solver directory"),
        ("src/math", "Math utilities directory"),
        ("python", "Python package directory"),
        ("python/gui", "GUI subpackage directory"),
        ("python/viz", "Visualization subpackage directory"),
        ("python/io", "I/O subpackage directory"),
        ("infra", "Infrastructure directory"),
    ]
    for dirname, desc in directories:
        total_checks += 1
        if check_dir(project_root / dirname, desc):
            passed_checks += 1
    
    # Summary
    print_header("Validation Summary")
    
    percentage = (passed_checks / total_checks * 100) if total_checks > 0 else 0
    
    print(f"Total Checks: {total_checks}")
    print(f"Passed: {GREEN}{passed_checks}{RESET}")
    print(f"Failed: {RED}{total_checks - passed_checks}{RESET}")
    print(f"Success Rate: {GREEN if percentage == 100 else YELLOW}{percentage:.1f}%{RESET}")
    
    if percentage == 100:
        print(f"\n{GREEN}{BOLD}[SUCCESS] All project structure checks passed!{RESET}")
        print(f"{GREEN}SPIKE repository structure is valid.{RESET}\n")
        return 0
    else:
        print(f"\n{RED}{BOLD}[WARNING] Some checks failed.{RESET}")
        print(f"{YELLOW}Please review the missing files/directories above.{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
