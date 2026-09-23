# SPIKE v0.1.7.0 - Quick Reference Guide

## 🚀 **Quick Start**

### **1. Build the C++ Solver**
```bash
cd C:\Users\example\Documents\agws\KiCAD_plugins\SPIKE
cmake -B build -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build build --config Release
```

### **2. Run Unit Tests**
```bash
cd build\Release
test_peec.exe
```

### **3. Install KiCad Plugin**
```bash
install_plugin.bat
```

### **4. Use in KiCad**
```
1. Open KiCad
2. Open a PCB file
3. Tools > External Plugins > SPIKE
```

---

## 📋 **Command Reference**

### **Build Commands**

| Command | Description |
|---------|-------------|
| `cmake -B build` | Configure build system |
| `cmake --build build --config Release` | Build release version |
| `cmake --build build --config Debug` | Build debug version |
| `cmake --build build --target test_peec` | Build only tests |

### **Test Commands**

| Command | Description |
|---------|-------------|
| `build\Release\test_peec.exe` | Run all unit tests |
| `ctest --test-dir build` | Run tests via CTest |

### **Plugin Commands**

| Command | Description |
|---------|-------------|
| `install_plugin.bat` | Install/update plugin |
| `clean_cache.bat` | Clear Python cache |

---

## 🔧 **Troubleshooting**

### **Build Issues**

**Problem:** CMake can't find Eigen3
```bash
# Solution: Specify vcpkg toolchain
cmake -B build -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake
```

**Problem:** OpenMP not found
```bash
# Solution: Use MSVC compiler (not MinGW)
# Ensure Visual Studio is installed
```

### **Plugin Issues**

**Problem:** KiCad shows old version (v0.1.6.0)
```bash
# Solution 1: Clear cache and reinstall
clean_cache.bat
install_plugin.bat
# Then restart KiCad

# Solution 2: Manual verification
notepad "%USERPROFILE%\Documents\KiCad\9.0\3rdparty\plugins\SPIKE\__init__.py"
# Check line 5 shows: Version: 0.1.7.0
```

**Problem:** Plugin doesn't appear
```bash
# Solution: Check installation path
dir "%USERPROFILE%\Documents\KiCad\9.0\3rdparty\plugins\SPIKE"
# Should show __init__.py and metadata.json
```

---

## 📊 **File Locations**

### **Source Code**
```
C:\Users\example\Documents\agws\KiCAD_plugins\SPIKE\
├── src\peec\peec_solver.cpp      # PEEC implementation
├── src\peec\peec_solver.hpp      # PEEC interface
├── tests\test_peec.cpp           # Unit tests
└── CMakeLists.txt                # Build configuration
```

### **Build Output**
```
C:\Users\example\Documents\agws\KiCAD_plugins\SPIKE\build\Release\
├── spike_peec.lib                # PEEC library
├── spike_thermal.lib             # Thermal library
├── test_peec.exe                 # Test executable
└── spike_core.pyd                # Python module (Phase 5)
```

### **Plugin Installation**
```
C:\Users\example\Documents\KiCad\9.0\3rdparty\plugins\SPIKE\
├── __init__.py                   # Plugin code
├── metadata.json                 # Plugin metadata
└── __pycache__\                  # Python cache (auto-generated)
```

---

## 🎯 **Common Tasks**

### **Update Plugin After Code Changes**
```bash
# 1. Rebuild C++ code (if changed)
cmake --build build --config Release

# 2. Reinstall plugin
install_plugin.bat

# 3. Restart KiCad
```

### **Run Tests After Changes**
```bash
# Rebuild and run
cmake --build build --config Release --target test_peec
build\Release\test_peec.exe
```

### **Clean Build**
```bash
# Remove build directory
rmdir /S /Q build

# Reconfigure and rebuild
cmake -B build -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build build --config Release
```

---

## 📚 **API Reference**

### **C++ API**

```cpp
#include "peec/peec_solver.hpp"

using namespace spike::peec;

// Create solver
PEECSolver solver;

// Add filament
Filament fil;
fil.start = Point3D(0, 0, 0);
fil.end = Point3D(10, 0, 0);
fil.width = 0.5;
fil.thickness = 0.035;
solver.add_filament(fil);

// Compute inductance
auto L = solver.compute_partial_inductance();
double L_self = L.coeff(0, 0);  // Self-inductance in H
```

### **Python API** (Phase 5)

```python
import spike_core

# Create solver
solver = spike_core.PEECSolver()

# Add filament
fil = spike_core.Filament()
fil.start = spike_core.Point3D(0, 0, 0)
fil.end = spike_core.Point3D(10, 0, 0)
fil.width = 0.5
fil.thickness = 0.035
solver.add_filament(fil)

# Compute inductance
L = solver.compute_partial_inductance()
L_self = L[0,0]  # Self-inductance in H
print(f"{L_self*1e9:.2f} nH")  # Convert to nH
```

---

## 🔢 **Unit Conversions**

| Quantity | Input (Code) | Output (SI) | Display |
|----------|--------------|-------------|---------|
| Length | mm | m | mm |
| Width | mm | m | mm |
| Thickness | mm | m | μm |
| Inductance | H | H | nH (×10⁹) |
| Resistance | Ω | Ω | mΩ (×10³) |
| Capacitance | F | F | pF (×10¹²) |

**Example:**
```cpp
// Input: 10mm trace
fil.start = Point3D(0, 0, 0);
fil.end = Point3D(10, 0, 0);  // 10mm

// Output: 8.27e-9 H
double L = solver.compute_partial_inductance().coeff(0,0);

// Display: 8.27 nH
std::cout << L * 1e9 << " nH" << std::endl;
```

---

## 📈 **Performance Tips**

### **Optimize Computation**

1. **Use Release Build**
   ```bash
   cmake --build build --config Release  # Not Debug!
   ```

2. **Enable OpenMP**
   - Automatically enabled with MSVC
   - Uses all available CPU cores

3. **Reduce Filament Count**
   - Combine short segments
   - Use coarser discretization

### **Expected Performance**

| Filaments | Matrix Size | Time (Release) | Memory |
|-----------|-------------|----------------|--------|
| 10 | 10×10 | <1 ms | <1 MB |
| 100 | 100×100 | ~10 ms | ~1 MB |
| 1,000 | 1000×1000 | ~100 ms | ~10 MB |
| 3,188 | 3188×3188 | ~2 sec | ~100 MB |

---

## 🎨 **Color Schemes**

### **Results Visualization**

| Colormap | Use Case |
|----------|----------|
| `jet` | General purpose |
| `viridis` | Perceptually uniform |
| `plasma` | High contrast |
| `coolwarm` | Diverging data |
| `RdYlGn` | Red (bad) to Green (good) |

**Example:**
```python
viewport.show_results(inductance_values, colormap='jet')
```

---

## 📞 **Support**

### **Documentation**
- `README.md` - Project overview
- `PROJECT_SUMMARY.md` - Complete summary
- `TROUBLESHOOTING.md` - Common issues
- `UI_ROADMAP.md` - UI development plan

### **Test Files**
- `tests/test_peec.cpp` - C++ unit tests
- `test_bindings.py` - Python bindings tests

### **Demo Files**
- `demo_spike.py` - Full demo application

---

**Quick Reference v0.1.7.0** | Last Updated: 2026-02-08
