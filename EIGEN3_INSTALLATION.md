# SPIKE v0.1.7.0 - Eigen3 Installation Guide

## 🎯 Objective

Install the Eigen3 C++ linear algebra library to enable compilation of SPIKE's C++ kernel.

---

## 📦 What is Eigen3?

**Eigen** is a C++ template library for linear algebra: matrices, vectors, numerical solvers, and related algorithms.

- **Website:** https://eigen.tuxfamily.org/
- **Version Required:** 3.4.0+
- **License:** MPL2 (permissive, compatible with commercial use)
- **Why:** Industry-standard for scientific C++ (used by Google, NASA, etc.)

---

## 🪟 Installation on Windows

### Option 1: vcpkg (Recommended for Windows)

**vcpkg** is Microsoft's C++ package manager.

#### Step 1: Install vcpkg (if not already installed)

```powershell
# Clone vcpkg
cd C:\
git clone https://github.com/Microsoft/vcpkg.git
cd vcpkg

# Bootstrap vcpkg
.\bootstrap-vcpkg.bat

# Add to PATH (optional but recommended)
$env:PATH += ";C:\vcpkg"
```

#### Step 2: Install Eigen3

```powershell
# Install Eigen3
.\vcpkg install eigen3:x64-windows

# Integrate with Visual Studio (optional)
.\vcpkg integrate install
```

#### Step 3: Verify Installation

```powershell
# Check installation
.\vcpkg list | Select-String "eigen"
```

**Expected Output:**
```
eigen3:x64-windows    3.4.0    C++ template library for linear algebra
```

---

### Option 2: Manual Download (Alternative)

#### Step 1: Download Eigen3

1. Go to: https://gitlab.com/libeigen/eigen/-/releases
2. Download latest stable release (e.g., `eigen-3.4.0.zip`)
3. Extract to: `C:\Libraries\eigen-3.4.0\`

#### Step 2: Set Environment Variable

```powershell
# Add EIGEN3_DIR environment variable
[System.Environment]::SetEnvironmentVariable('EIGEN3_DIR', 'C:\Libraries\eigen-3.4.0', 'User')

# Reload environment
$env:EIGEN3_DIR = 'C:\Libraries\eigen-3.4.0'
```

---

## 🐧 Installation on Linux

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install libeigen3-dev
```

### Fedora/RHEL

```bash
sudo dnf install eigen3-devel
```

### Arch Linux

```bash
sudo pacman -S eigen
```

---

## 🍎 Installation on macOS

### Using Homebrew

```bash
brew install eigen
```

---

## 🔧 Configuring CMake to Find Eigen3

SPIKE's `CMakeLists.txt` is already configured to find Eigen3. It will search in:

1. **vcpkg** (if integrated)
2. **System paths** (`/usr/include/eigen3`, `/usr/local/include/eigen3`)
3. **EIGEN3_DIR** environment variable

### CMake Configuration

```cmake
# From SPIKE/CMakeLists.txt
find_package(Eigen3 3.4 REQUIRED NO_MODULE)
target_link_libraries(spike_peec PRIVATE Eigen3::Eigen)
```

---

## ✅ Verification

After installation, verify Eigen3 is accessible:

### Test with CMake

```powershell
# Create build directory
cd C:\Users\example\Documents\agws\KiCAD_plugins\SPIKE
mkdir build
cd build

# Run CMake configuration
cmake ..
```

**Expected Output:**
```
-- Found Eigen3: C:/vcpkg/installed/x64-windows/share/eigen3 (found version "3.4.0")
-- Configuring done
-- Generating done
```

### Test with Simple C++ Program

Create `test_eigen.cpp`:

```cpp
#include <Eigen/Dense>
#include <iostream>

int main() {
    Eigen::MatrixXd m(2,2);
    m(0,0) = 3;
    m(1,0) = 2.5;
    m(0,1) = -1;
    m(1,1) = m(1,0) + m(0,1);
    std::cout << "Eigen3 is working!\n";
    std::cout << m << std::endl;
    return 0;
}
```

Compile and run:

```powershell
# Using MSVC
cl /EHsc /I"C:\vcpkg\installed\x64-windows\include" test_eigen.cpp
.\test_eigen.exe

# Or using CMake
cmake -B build -S .
cmake --build build
.\build\test_eigen.exe
```

---

## 🚀 Next Steps After Eigen3 Installation

Once Eigen3 is installed:

1. **Build SPIKE C++ Kernel**
   ```powershell
   cd C:\Users\example\Documents\agws\KiCAD_plugins\SPIKE
   mkdir build
   cd build
   cmake ..
   cmake --build . --config Release
   ```

2. **Implement PEEC Solver**
   - `compute_partial_inductance()` - Neumann formula with Gaussian quadrature
   - `compute_partial_capacitance()` - Maxwell capacitance matrix
   - `compute_resistance()` - DC resistance calculation

3. **Create Python Bindings**
   - Install nanobind
   - Create Python module
   - Test from Python

---

## 📚 Eigen3 Resources

- **Official Documentation:** https://eigen.tuxfamily.org/dox/
- **Quick Reference:** https://eigen.tuxfamily.org/dox/group__QuickRefPage.html
- **Tutorial:** https://eigen.tuxfamily.org/dox/GettingStarted.html

---

## 🐛 Troubleshooting

### CMake Can't Find Eigen3

**Solution 1:** Set `EIGEN3_DIR` environment variable
```powershell
$env:EIGEN3_DIR = "C:\vcpkg\installed\x64-windows\share\eigen3"
```

**Solution 2:** Specify path in CMake command
```powershell
cmake -DEIGEN3_DIR="C:\vcpkg\installed\x64-windows\share\eigen3" ..
```

### vcpkg Integration Issues

```powershell
# Re-integrate vcpkg
cd C:\vcpkg
.\vcpkg integrate install

# Use vcpkg toolchain file
cmake -DCMAKE_TOOLCHAIN_FILE=C:\vcpkg\scripts\buildsystems\vcpkg.cmake ..
```

---

**Ready to install Eigen3!** Choose your preferred method and proceed.
