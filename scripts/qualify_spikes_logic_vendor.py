# SPDX-License-Identifier: Apache-2.0
"""Reference-engine DC checks of local, unmodified TI single-gate archives.

No model download, redistribution, native SPIKES qualification or electrical
package synthesis is performed. Helper subcircuits never count as extra parts.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

MODELS = {
    'SN74HC10': ('SN74HC10.cir', '63428d080cb27cd3b552f4b7ea53f19db4cd0e5ef054f51a7c74d7024e79b9c3',
                 'https://www.ti.com/lit/zip/sclm227', 'nand'),
    'SN74HC11': ('SN74HC11.cir', 'b8ebc0bf360d17cdb48c463c374036bbb6e3e035556afdee33c26b50ff2cbf09',
                 'https://www.ti.com/lit/zip/sclm226', 'and'),
}


def check_archive(part, archive_path, engine):
    """Strict pinned revision, 25 C, 5 V, 10 kohm loaded truth table only."""
    if part not in MODELS:
        raise ValueError('No reviewed testbench for this part')
    member, expected_digest, url, operation = MODELS[part]
    path = Path(archive_path)
    if path.stat().st_size > 1024*1024:
        raise ValueError('Archive exceeds 1 MiB')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_digest:
        raise ValueError('Model archive revision differs; review and create a new qualification record')
    with zipfile.ZipFile(path) as archive:
        if archive.namelist() != [member] or archive.getinfo(member).file_size > 256*1024:
            raise ValueError('Unexpected archive members')
        original = archive.read(member)
    # Normalize transport line endings only; do not translate model constructs.
    model = original.decode('ascii').replace('\r\r\n', '\n').replace('\r\n', '\n')
    cases = []
    with tempfile.TemporaryDirectory(prefix='spikes-ti-gate-') as directory:
        workspace = Path(directory)
        (workspace/'.spiceinit').write_text('set ngbehavior=ps\n', encoding='ascii')
        (workspace/'original.cir').write_text(model, encoding='ascii')
        for bits in itertools.product((0, 1), repeat=3):
            deck = ('TI single-gate DC reference test\n.include original.cir\n'
                    'Vs supply 0 5\n.temp 25\n'
                    + ''.join(f'V{pin} {pin} 0 {5*value}\n' for pin, value in zip('abc', bits))
                    + f'Xgate out a b c supply 0 {part}\nRload out 0 10k\n.op\n'
                    '.control\nrun\nprint v(out)\nquit\n.endc\n.end\n')
            (workspace/'bench.cir').write_text(deck, encoding='ascii')
            process = subprocess.run([str(Path(engine).resolve()), '-b', 'bench.cir'], cwd=workspace,
                                     capture_output=True, text=True, timeout=20)
            output = process.stdout + process.stderr
            values = re.findall(r'v\(out\)\s*=\s*([-+0-9.eE]+)', output, re.I)
            high = all(bits) if operation == 'and' else not all(bits)
            voltage = float(values[-1]) if values else None
            passed = (process.returncode == 0 and voltage is not None
                      and (4.8 <= voltage <= 5.1 if high else -.1 <= voltage <= .2))
            cases.append(dict(inputs=list(bits), expected_logic=int(high), voltage_v=voltage,
                              passed=passed, diagnostics=output[-1200:] if not passed else ''))
    return dict(part=part, archive_sha256=digest, member_sha256=hashlib.sha256(original).hexdigest(),
                source_url=url, backend='explicit_ngspice_ps_compatibility',
                engine_sha256=hashlib.sha256(Path(engine).read_bytes()).hexdigest(),
                conditions=dict(supply_v=5, temperature_c=25, load_ohm=10000),
                unit='single_gate_not_complete_package', cases=cases,
                passed=all(case['passed'] for case in cases),
                qualification='reference_dc_truth_table_only', manufacturer_qualified=False,
                native_spikes_qualified=False, redistribution='not_established',
                exclusions=['transient timing', 'temperature sweep', 'supply sweep', 'noise',
                            'full package power consumption', 'hardware measurement agreement'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--intake-dir', type=Path, required=True)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Refusing to replace prior evidence')
    results = [check_archive(part, args.intake_dir/(item[1]+'.download'), args.ngspice)
               for part, item in MODELS.items()]
    report = dict(contract='spikes/vendor-logic-reference/v1', models=results,
                  passed=all(item['passed'] for item in results), release_qualification=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'], parts=len(results),
                         cases=sum(len(item['cases']) for item in results), report=str(args.output))))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
