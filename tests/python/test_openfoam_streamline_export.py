# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.solvers.external_engines.openfoam.openfoam_streamline_export import _curves, export_forced_airflow_field_volume


def encoded(kind, values):
    code = {"Float32": "f", "Int32": "i"}[kind]
    payload = struct.pack("<" + code * len(values), *values)
    return base64.b64encode(struct.pack("<Q", len(payload)) + payload).decode()


def vtp(connectivity=(0, 1), *, points=(0, 0, 0, .001, 0, 0)):
    arrays = {
        "Points": ("Float32", points), "T": ("Float32", [298, 299]),
        "U": ("Float32", [1, 0, 0, 2, 0, 0]), "connectivity": ("Int32", connectivity),
        "offsets": ("Int32", [2]),
    }
    body = "".join(f'<DataArray type="{kind}" Name="{name}" format="binary">{encoded(kind, values)}</DataArray>'
                   for name, (kind, values) in arrays.items())
    return (f'<VTKFile type="PolyData" byte_order="LittleEndian" header_type="UInt64">'
            f'<PolyData><Piece NumberOfPoints="2" NumberOfLines="1"><Points>{body}</Points></Piece></PolyData></VTKFile>')


class OpenFoamStreamlineExportTests(unittest.TestCase):
    def test_reads_aligned_native_vtp_tracks(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "track0.vtp"
            path.write_text(vtp(), encoding="utf-8")
            curves = _curves(path)
        self.assertAlmostEqual(curves[0]["points"][1][0], 1.0, places=6)
        self.assertEqual(curves[0]["points"][1][1:], [0.0, 0.0])
        self.assertEqual(curves[0]["scalars"]["speed_m_s"], [1.0, 2.0])

    def test_rejects_negative_connectivity_and_truncated_payload(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "track0.vtp"
            path.write_text(vtp(connectivity=(-1, 1)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "connectivity"):
                _curves(path)
            malformed = vtp().replace(encoded("Float32", [298, 299]), encoded("Float32", [298, 299])[:-4])
            path.write_text(malformed, encoding="utf-8")
            with self.assertRaises((ValueError, struct.error)):
                _curves(path)

    def test_exports_saved_frames_under_field_volume_contract(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            case = Path(directory)
            (case / "system").mkdir()
            (case / "0.1/air").mkdir(parents=True)
            (case / "0.1/air/U").write_text("field", encoding="utf-8")
            (case / "0.1/air/T").write_text("field", encoding="utf-8")
            result = {"status": "completed", "job_id": "fixture", "fields": {"velocity_m_s": {"samples": [
                {"region": "air", "point_mm": [1, 2, 3], "value": [1, 0, 0]}]}}}
            cancellation = threading.Event()
            with patch('python.spike_core.solvers.external_engines.openfoam.openfoam_streamline_export._bounded_command', return_value=['solver']), \
                 patch('python.spike_core.solvers.external_engines.openfoam.openfoam_streamline_export.run_adapter_process', return_value={'return_code': 0, 'stdout': 'Tracks: 1'}) as process, \
                 patch('python.spike_core.solvers.external_engines.openfoam.openfoam_streamline_export._windows_process_allowance', return_value=None), \
                 patch('python.spike_core.solvers.external_engines.openfoam.openfoam_streamline_export._parse_internal_field', side_effect=[[[1, 0, 0]], [298.25]]), \
                 patch('python.spike_core.solvers.external_engines.openfoam.openfoam_streamline_export._curves', return_value=[{'points': [[1,2,3],[2,2,3]], 'scalars': {'temperature_k':[298,298], 'speed_m_s':[1,1]}}]):
                field = export_forced_airflow_field_volume(case, result, seed_line_mm=[[0,0,0],[0,1,0]], runtime={'kind': 'test'}, cancellation_event=cancellation)
        self.assertEqual(field["contract"], "spike/field-volume-view/v1")
        self.assertEqual(field["frames"][0]["timeS"], .1)
        self.assertEqual(field["frames"][0]["scalars"]["temperature_k"], [298.25])
        self.assertEqual(len(field["frames"][0]["streamlines"]), 1)
        self.assertIs(process.call_args.kwargs["cancellation_event"], cancellation)


if __name__ == "__main__":
    unittest.main()
