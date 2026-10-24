# SPDX-License-Identifier: Apache-2.0
"""Explicit experimental worker routes for immutable geometry-derived ports."""
from .service_helpers import error_response


def handle_geometry_pod_request(method,params):
    if method not in {'propulsion_pod_geometry_capabilities','validate_propulsion_pod_geometry','run_propulsion_pod_geometry'}:
        return None
    try:
        if method=='propulsion_pod_geometry_capabilities':
            if params!={}:raise ValueError('Capabilities accepts no parameters')
            return {'ok':True,'result':{'result_contract':'spike/geometry-propulsion-loop-result/v1',
                'model_status':'experimental','production_qualified':False,
                'inputs':'Explicit immutable periodic magnetic coenergy and retained CFD tables; no automatic source/grid qualification',
                'controller':'Fixed built-in compiled C demonstration controller, not VESC firmware',
                'thermal':'Eleven-node supplied thermal network with resistance feedback; not resolved CHT',
                'fluid':'Quasi-steady supplied CFD-anchor interpolation, not a new fluid solve or unsteady wake'}}
        from .propulsion_pod_geometry_run import prepare_geometry_run,execute_geometry_run
        if method=='validate_propulsion_pod_geometry':
            request,_,_,diagnostics=prepare_geometry_run(params)
            return {'ok':True,'result':{'request':request,'diagnostics':diagnostics}}
        return {'ok':True,'result':execute_geometry_run(params)}
    except (ValueError,TypeError,KeyError,ArithmeticError,RuntimeError,OSError) as exc:
        return error_response('SPIKE-BE-IPC-E-0001','Geometry propulsion loop failed.',
            detail=str(exc),context={'method':method},error_type=type(exc).__name__)
