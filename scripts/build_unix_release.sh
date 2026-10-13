#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
export RUSTFLAGS="--remap-path-prefix=$PWD=/build/spike --remap-path-prefix=$HOME=/build/user"
export CFLAGS="${CFLAGS:-} -ffile-prefix-map=$PWD=/build/spike"
export CXXFLAGS="${CXXFLAGS:-} -ffile-prefix-map=$PWD=/build/spike"
python -m pip install numpy scipy shapely matplotlib mplcursors reportlab nanobind jsonschema==4.25.1 pyarrow==25.0.1 pyinstaller==6.21.0
cmake_args=(-DCMAKE_BUILD_TYPE=Release -DBUILD_PYTHON_BINDINGS=ON -DSPIKE_PORTABLE_BUILD=ON
  "-DPython_EXECUTABLE=$(command -v python)" "-Dnanobind_DIR=$(python -m nanobind --cmake_dir)")
if [[ "$(uname)" == Darwin ]]; then
  export CC="$(brew --prefix llvm)/bin/clang"
  export CXX="$(brew --prefix llvm)/bin/clang++"
  git clone --depth 1 --branch 3.4.0 https://gitlab.com/libeigen/eigen.git build/eigen-source
  cmake -S build/eigen-source -B build/eigen-config -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX="$PWD/build/eigen"
  cmake --install build/eigen-config
  cmake_args+=("-DOpenMP_ROOT=$(brew --prefix libomp)" "-DCMAKE_PREFIX_PATH=$PWD/build/eigen;$(brew --prefix libomp)")
fi
cmake -S . -B build-spikes-hybrid -G Ninja "${cmake_args[@]}"
cmake --build build-spikes-hybrid --target spike_peec_native spikes_c_api --parallel 2
python scripts/build_packaged_worker.py
python scripts/verify_packaged_cli.py -- app/src-tauri/resources/worker/spike-worker/spike-worker --cli
cd app
npm ci
npm run build
cd ..
python scripts/prepare_release_resources.py --config-output build/tauri.release.json
cd app
if [[ "$(uname)" == Darwin ]]; then
  npm run tauri build -- --bundles app --config ../build/tauri.release.json
else
  npm run tauri build -- --bundles deb --config ../build/tauri.release.json
fi
