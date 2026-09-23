"""Fail-closed release evidence and Qt-free payload checks.

Evidence is supplied by qualification jobs and reviewers, not invented from
feature flags. Passing this structural check does not itself qualify physics.
"""
import hashlib
import json
from pathlib import Path
import re

CONTRACT='spikes/release-evidence/v1'
GATES={
    'gui_workflows':'Windows and Linux actual GUI workflows',
    'project_migration':'Project migration, hierarchy and loss-report roundtrips',
    'custom_dynamic_device':'User-defined charge/state device without solver edits',
    'spice_compatibility':'Published SPICE3 and backend/dialect matrix',
    'semiconductor_dynamics':'Dynamic semiconductor models and applicable analyses',
    'igbt_qualification':'Reviewed IGBT conduction, charge, tail, switching and thermal evidence',
    'thyristor_qualification':'Reviewed thyristor trigger, latch, hold, recovery and commutation evidence',
    'manufacturer_catalog':'Every downloaded model in the frozen manufacturer catalog',
    'converter_rf_motor':'Equal-model converter, RF, motor and battery/control corpus',
    'continuous_control':'Pause/resume, bounded capture, worker faults and disconnected I/O',
    'mixed_signal':'Compiled C/C++/HDL controllers and analog/digital timing',
    'plot_correctness':'Sweep selection, exact measurements and linked cursors',
    'performance':'Recorded reference hardware, latency, memory and thread scaling',
    'offline_qt_free':'Offline operation and packaged Qt-free dependency inventory',
    'windows_package':'Installed Windows package verification and rollback',
    'linux_package':'Linux AppImage verification',
    'redistribution':'Reviewed dependency/model rights, SBOM, notices and final EULA',
    'help_examples':'Actual application screenshots and executable bundled examples',
}


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def evaluate(evidence,root,*,candidate_sha256=None):
    root=Path(root).resolve();issues=[];gates={}
    if not isinstance(evidence,dict):evidence={}
    if evidence.get('contract')!=CONTRACT:issues.append('Missing or unsupported release evidence contract')
    if candidate_sha256 is not None and evidence.get('candidate_sha256')!=candidate_sha256:
        issues.append('Qualification evidence does not match this candidate source manifest')
    records=evidence.get('gates',{})
    if not isinstance(records,dict):records={}
    for ident,description in GATES.items():
        record=records.get(ident);problems=[]
        if not isinstance(record,dict):record={}
        if record.get('status')!='passed':problems.append('not passed')
        reviewer=record.get('reviewed_by')
        if not isinstance(reviewer,str) or not reviewer.strip():problems.append('no reviewer')
        checks=record.get('checks',{})
        if not isinstance(checks,dict) or type(checks.get('total')) is not int or checks.get('total',0)<1 or type(checks.get('failed')) is not int or checks.get('failed')!=0 or type(checks.get('skipped')) is not int or checks.get('skipped')!=0:
            problems.append('checks missing, failed or skipped')
        artifacts=record.get('artifacts',[])
        if not isinstance(artifacts,list) or not artifacts:
            problems.append('no evidence artifacts');artifacts=[]
        for artifact in artifacts:
            if not isinstance(artifact,dict) or not isinstance(artifact.get('path'),str) or not isinstance(artifact.get('sha256'),str):
                problems.append('invalid artifact record');continue
            path=(root/artifact['path']).resolve()
            if Path(artifact['path']).is_absolute() or not path.is_relative_to(root):
                problems.append('artifact outside evidence root');continue
            if not path.is_file() or digest(path)!=artifact['sha256']:problems.append('missing or changed artifact: '+artifact['path'])
        gates[ident]=dict(description=description,passed=not problems,issues=problems)
    return dict(contract='spikes/release-gate-report/v1',releasable=not issues and all(g['passed'] for g in gates.values()),issues=issues,gates=gates)


def require_evidence(path,candidate_sha256):
    path=Path(path)
    if path.stat().st_size>4*1024*1024:raise ValueError('Release evidence exceeds 4 MiB')
    report=evaluate(json.loads(path.read_text(encoding='utf-8')),path.parent,candidate_sha256=candidate_sha256)
    if not report['releasable']:
        failures=[key for key,value in report['gates'].items() if not value['passed']]
        raise ValueError('Release blocked: '+', '.join(report['issues']+failures))
    return report


def qt_dependencies(names):
    """Inspect actual frozen module/payload names, not strings in help text."""
    blocked=[]
    for name in names:
        normalized=str(name).replace('\\','/').lower()
        segments=re.split(r'[/.:\-]',normalized)
        if any(s in {'pyqt4','pyqt5','pyqt6','pyside','pyside2','pyside6','pyqtgraph','qtpy','pyvistaqt','qvtk'} for s in segments) or re.search(r'(?:^|/)(?:lib)?qt[456][a-z0-9_]*(?:\.dll|\.so|\.dylib|\.framework)(?:\.|$)',normalized) or 'vtkmodules.qt' in normalized:
            blocked.append(str(name))
    return sorted(set(blocked))
