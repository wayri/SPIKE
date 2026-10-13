# SPDX-License-Identifier: Apache-2.0
"""Admit retained EM study records without implying numerical qualification."""
import math
from .assembly_field_handoff import bounded_json, field_resource_limits
from .assembly_em import prepare_assembly_em


def admit_assembly_em_study(record):
    if not isinstance(record, dict) or set(record) != {'contract', 'request', 'result'}:
        raise ValueError('ASSEMBLY_EM_STUDY: exact contract/request/result required')
    limits=field_resource_limits(record.get('request',{}).get('geometry',{}))
    bounded_json(record,max_bytes=limits['max_control_bytes'])
    if record['contract'] != 'spike/assembly-em-study/v1':
        raise ValueError('ASSEMBLY_EM_STUDY: unsupported contract')
    prepared = prepare_assembly_em(record['request'])
    result = record['result']
    if result is None:
        return record
    if not isinstance(result, dict) or result.get('contract') != 'spike/assembly-em-result/v1':
        raise ValueError('ASSEMBLY_EM_STUDY: incompatible result')
    if (result.get('request_digest') != prepared['request_digest']
            or result.get('compiled_digest') != prepared['compiled']['compiled_digest']
            or result.get('assembly_digest') != prepared['assembly_digest']
            or result.get('frequency_hz') != prepared['settings']['frequency_hz']
            or result.get('status') != 'completed' or result.get('solver_executed') is not True
            or result.get('production_qualified') is not False or result.get('model_status') != 'unvalidated'):
        raise ValueError('ASSEMBLY_EM_STUDY: result is stale or has incompatible status')
    ports = prepared['compiled']['ports']
    columns = result.get('s_parameter_column')
    if (not isinstance(columns, list) or [item.get('port_id') for item in columns] != [p['id'] for p in ports]
            or result.get('excited_port_id') != next(p['id'] for p in ports if p['excite'])):
        raise ValueError('ASSEMBLY_EM_STUDY: port identities differ')
    count = len(result['frequency_hz'])
    for column in columns:
        for key in ('real', 'imag'):
            values = column.get(key)
            if not isinstance(values, list) or len(values) != count or any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise ValueError('ASSEMBLY_EM_STUDY: malformed complex port samples')
    preview = result.get('field_capture', {}).get('preview')
    if preview is not None:
        if (preview.get('contract') != 'spike/assembly-em-preview/v1'
                or preview.get('normalization') != '1V_peak_incident'
                or preview.get('coordinate_frame') != 'assembly' or preview.get('coordinate_units') != 'm'
                or preview.get('frequency_hz') != result['frequency_hz'][-1]
                or set(preview.get('datasets', {})) != {'electric-field', 'magnetic-field'}):
            raise ValueError('ASSEMBLY_EM_STUDY: incompatible field normalization/frame')
        for name, dataset in preview['datasets'].items():
            positions, vectors, indices = (dataset.get(key) for key in ('positions_m', 'vectors', 'native_indices'))
            if (not isinstance(positions, list) or not 1 <= len(positions) <= 8000
                    or not isinstance(vectors, list) or len(vectors) != len(positions)
                    or not isinstance(indices, list) or len(indices) != len(positions)
                    or dataset.get('units') != ('V/m' if name == 'electric-field' else 'A/m')
                    or type(dataset.get('source_sample_count')) is not int
                    or dataset['source_sample_count'] < len(positions)
                    or any(type(i) is not int or not 0 <= i < dataset['source_sample_count'] for i in indices)
                    or len(set(indices)) != len(indices)):
                raise ValueError('ASSEMBLY_EM_STUDY: malformed field samples')
            for point, vector in zip(positions, vectors):
                if (not isinstance(point, list) or len(point) != 3
                        or not isinstance(vector, list) or len(vector) != 3
                        or any(not isinstance(pair, list) or len(pair) != 2 for pair in vector)
                        or any(type(v) not in (int, float) or not math.isfinite(v)
                               for v in point + [v for pair in vector for v in pair])):
                    raise ValueError('ASSEMBLY_EM_STUDY: nonfinite or malformed field vector')
    return record
