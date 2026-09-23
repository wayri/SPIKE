#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v npm >/dev/null || { echo "Node.js/npm is required for building; it is not shipped in the runtime app." >&2; exit 1; }
command -v cargo >/dev/null || { echo "Rust/cargo is required" >&2; exit 1; }

if [[ ! -x .venv/bin/python3 ]]; then
  python3 -m venv .venv
fi
.venv/bin/python3 -m pip install --disable-pip-version-check -r requirements.txt

cd app
npm ci --ignore-scripts
npm run build
npm run tauri build
