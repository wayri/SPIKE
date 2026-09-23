"""
SPIKE: Signal, Power, and Integrity Knowledge Engine
Infrastructure Bootstrap - aether_boot.py

Purpose: Isolated Python environment management for SPIKE
Version: 0.1.6.0

This module provides:
1. Virtual environment creation and activation
2. Dependency installation (wxPython, PyVista, nanobind, etc.)
3. Environment validation
4. Cross-platform compatibility (Windows/Linux)

Usage:
    python infra/aether_boot.py --init      # Create environment
    python infra/aether_boot.py --validate  # Check dependencies
    python infra/aether_boot.py --activate  # Print activation command
"""

import sys
import subprocess
import venv
import os
from pathlib import Path
from typing import List, Tuple

# SPIKE root directory
SPIKE_ROOT = Path(__file__).parent.parent.absolute()
VENV_DIR = SPIKE_ROOT / "aether_env"

# Required Python packages with minimum versions
REQUIRED_PACKAGES = [
    "wxPython>=4.2.0",
    "pyvista>=0.43.0",
    "numpy>=1.24.0",
    "scipy>=1.10.0",
    "matplotlib>=3.7.0",
    # nanobind will be installed via pip in v0.1.7.0
    # "nanobind>=1.8.0",
]

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(msg: str):
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{msg:^70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_success(msg: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}[OK] {msg}{Colors.ENDC}")


def print_error(msg: str):
    """Print error message"""
    print(f"{Colors.FAIL}[ERROR] {msg}{Colors.ENDC}")


def print_info(msg: str):
    """Print info message"""
    print(f"{Colors.OKCYAN}[INFO] {msg}{Colors.ENDC}")


def create_venv():
    """Create virtual environment"""
    print_header("Creating SPIKE Virtual Environment")
    
    if VENV_DIR.exists():
        print_info(f"Virtual environment already exists at: {VENV_DIR}")
        return True
    
    try:
        print_info(f"Creating venv at: {VENV_DIR}")
        venv.create(VENV_DIR, with_pip=True, clear=False)
        print_success("Virtual environment created successfully")
        return True
    except Exception as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False


def get_pip_executable() -> Path:
    """Get path to pip executable in virtual environment"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "pip.exe"
    else:
        return VENV_DIR / "bin" / "pip"


def get_python_executable() -> Path:
    """Get path to Python executable in virtual environment"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    else:
        return VENV_DIR / "bin" / "python"


def install_dependencies():
    """Install required Python packages"""
    print_header("Installing SPIKE Dependencies")
    
    pip_exe = get_pip_executable()
    
    if not pip_exe.exists():
        print_error(f"pip not found at: {pip_exe}")
        return False
    
    # Upgrade pip first
    print_info("Upgrading pip...")
    try:
        subprocess.run([str(pip_exe), "install", "--upgrade", "pip"], 
                      check=True, capture_output=True)
        print_success("pip upgraded")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to upgrade pip: {e}")
        return False
    
    # Install packages
    for package in REQUIRED_PACKAGES:
        print_info(f"Installing {package}...")
        try:
            subprocess.run([str(pip_exe), "install", package], 
                          check=True, capture_output=True)
            print_success(f"{package} installed")
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to install {package}: {e}")
            return False
    
    print_success("All dependencies installed successfully")
    return True


def validate_environment() -> bool:
    """Validate that all required packages are installed"""
    print_header("Validating SPIKE Environment")
    
    python_exe = get_python_executable()
    
    if not python_exe.exists():
        print_error(f"Python not found at: {python_exe}")
        return False
    
    all_valid = True
    
    for package in REQUIRED_PACKAGES:
        pkg_name = package.split(">=")[0].split("==")[0]
        try:
            result = subprocess.run(
                [str(python_exe), "-c", f"import {pkg_name.replace('-', '_').lower()}"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print_success(f"{pkg_name} is available")
            else:
                print_error(f"{pkg_name} is NOT available")
                all_valid = False
        except Exception as e:
            print_error(f"Failed to check {pkg_name}: {e}")
            all_valid = False
    
    if all_valid:
        print_success("Environment validation passed")
    else:
        print_error("Environment validation failed")
    
    return all_valid


def print_activation_command():
    """Print command to activate virtual environment"""
    print_header("Virtual Environment Activation")
    
    if sys.platform == "win32":
        activate_script = VENV_DIR / "Scripts" / "Activate.ps1"
        print_info("PowerShell:")
        print(f"    {activate_script}")
        print_info("CMD:")
        print(f"    {VENV_DIR / 'Scripts' / 'activate.bat'}")
    else:
        activate_script = VENV_DIR / "bin" / "activate"
        print_info("Bash/Zsh:")
        print(f"    source {activate_script}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="SPIKE Environment Bootstrap (aether_boot.py)"
    )
    parser.add_argument("--init", action="store_true", 
                       help="Initialize virtual environment and install dependencies")
    parser.add_argument("--validate", action="store_true",
                       help="Validate environment")
    parser.add_argument("--activate", action="store_true",
                       help="Print activation command")
    
    args = parser.parse_args()
    
    if args.init:
        if create_venv():
            if install_dependencies():
                print_activation_command()
                return 0
        return 1
    
    elif args.validate:
        return 0 if validate_environment() else 1
    
    elif args.activate:
        print_activation_command()
        return 0
    
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
