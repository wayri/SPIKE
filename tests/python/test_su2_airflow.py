# SPDX-License-Identifier: Apache-2.0
"""Original synthetic output oracles; never substituted for an actual SU2 run."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from spike_core.su2_airflow import cavity_mesh, parse_su2_cavity, run_su2_airflow, validate_su2_request


class Su2AirflowTests(unittest.TestCase):
    def test_admission_rejects_untrusted_paths_and_invalid_numbers(self):
        for request in ({'executable': 'bad'}, {'cells': True}, {'cells': 9}, {'reynolds': float('nan')},
                        {'reynolds': 0}, {'timeout_s': 99999}, {'iterations': 0}, {'case': 'assembly'}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                validate_su2_request(request)

    def test_mesh_covers_unit_area_with_positive_quads_and_closed_boundary(self):
        n = 8
        lines = cavity_mesh(n).splitlines()
        quads = [list(map(int, line.split()[1:])) for line in lines[2:2+n*n]]
        offset = 3+n*n
        points = [tuple(map(float, line.split())) for line in lines[offset:offset+(n+1)**2]]
        area = 0
        for quad in quads:
            polygon = [points[k] for k in quad]
            signed = sum(polygon[i][0]*polygon[(i+1)%4][1]-polygon[(i+1)%4][0]*polygon[i][1] for i in range(4))/2
            self.assertGreater(signed, 0)
            area += signed
        self.assertAlmostEqual(area, 1)
        edges = [tuple(map(int, line.split()[1:])) for line in lines if line.startswith('3 ')]
        self.assertEqual(len(edges), 4*n)
        self.assertEqual(sorted(a for a, b in edges), sorted(b for a, b in edges))

    def _fixture(self, directory, n=8):
        path = Path(directory) / 'solution.csv'
        with path.open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['PointID', 'x', 'y', 'Pressure', 'Velocity_x', 'Velocity_y'])
            for j in range(n+1):
                for i in range(n+1):
                    writer.writerow([j*(n+1)+i, i/n, j/n, i/n-j/n, 2*j/n, -3*i/n])
        (Path(directory) / 'history.csv').write_text('"rms[P]","rms[U]","rms[V]"\n-10,-11,-12\n')
        return path

    def test_exact_linear_centerlines_and_convergence(self):
        with tempfile.TemporaryDirectory() as directory:
            self._fixture(directory)
            result = parse_su2_cavity(directory, 8)
            self.assertTrue(result['convergence']['converged'])
            self.assertEqual(result['centerlines']['u'], [i/4 for i in range(9)])
            self.assertEqual(result['centerlines']['v'], [-3*i/8 for i in range(9)])
            (Path(directory) / 'history.csv').write_text('"rms[P]","rms[U]","rms[V]"\n-10,-2,-12\n')
            self.assertFalse(parse_su2_cavity(directory, 8)['convergence']['converged'])

    def test_rejects_duplicate_missing_nonfinite_and_wrong_coordinates(self):
        for kind in ('duplicate', 'missing', 'nonfinite', 'coordinates'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = self._fixture(directory)
                lines = path.read_text().splitlines()
                if kind == 'duplicate':
                    lines[-1] = lines[-2]
                elif kind == 'missing':
                    lines.pop()
                elif kind == 'nonfinite':
                    lines[-1] = lines[-1].replace('2.0', 'nan')
                else:
                    lines[1] = '0,0.2,0,0,0,0'
                path.write_text('\n'.join(lines))
                with self.assertRaises(ValueError):
                    parse_su2_cavity(directory, 8)

    def test_missing_runtime_and_cancel_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'SU2_UNAVAILABLE'):
                run_su2_airflow({}, executable=Path(directory)/'missing')
            with patch('spike_core.su2_airflow.find_su2', return_value=Path(sys.executable)):
                with self.assertRaisesRegex(RuntimeError, 'SU2_CANCELLED'):
                    run_su2_airflow({}, cancel_check=lambda: True)

    def test_changed_input_is_rejected_before_result_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'solver'
            executable.write_bytes(b'original synthetic executable identity')

            def changed_input(command, **options):
                (options['cwd'] / 'cavity.cfg').write_text('changed input')
                return {'return_code': 0, 'stdout': '', 'stderr': ''}

            with patch('spike_core.su2_airflow.run_adapter_process', side_effect=changed_input):
                with self.assertRaisesRegex(RuntimeError, 'SU2_INPUT_CHANGED'):
                    run_su2_airflow({'cells': 8}, executable=executable, output_root=directory)


if __name__ == '__main__':
    unittest.main()
