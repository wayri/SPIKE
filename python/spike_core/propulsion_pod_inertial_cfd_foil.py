# SPDX-License-Identifier: Apache-2.0
"""Geometric foil-section proxies for explicitly adapted ENOLA surfaces.

These are geometric screens, not airfoil identification or aerodynamic proof.
"""
import json,math
from pathlib import Path
import numpy as np


def section(poly,z_mm):
    import vtk
    plane=vtk.vtkPlane();plane.SetOrigin(0,0,z_mm);plane.SetNormal(0,0,1);cutter=vtk.vtkCutter();cutter.SetInputData(poly);cutter.SetCutFunction(plane);cutter.Update();clean=vtk.vtkCleanPolyData();clean.SetInputConnection(cutter.GetOutputPort());clean.SetToleranceIsAbsolute(1);clean.SetAbsoluteTolerance(1e-7);clean.Update();strip=vtk.vtkStripper();strip.SetInputConnection(clean.GetOutputPort());strip.JoinContiguousSegmentsOn();strip.Update();output=strip.GetOutput();ids=vtk.vtkIdList();lines=output.GetLines();lines.InitTraversal();loops=[]
    while lines.GetNextCell(ids):
        points=np.array([output.GetPoint(ids.GetId(i))[:2] for i in range(ids.GetNumberOfIds())])
        if len(points)>=4 and np.linalg.norm(points[0]-points[-1])<1e-5:loops.append(points)
    if not loops:raise ValueError('No closed foil section at z='+str(z_mm))
    points=max(loops,key=lambda p:abs(np.sum(p[:-1,0]*p[1:,1]-p[1:,0]*p[:-1,1])))
    cloud=points[:-1];distance=np.sum((cloud[:,None]-cloud[None,:])**2,axis=2);i,j=np.unravel_index(np.argmax(distance),distance.shape);a,b=cloud[i],cloud[j]
    if a[0]>b[0]:a,b=b,a
    chord=float(np.linalg.norm(b-a));e=(b-a)/chord;n=np.array([-e[1],e[0]]);s=(points-a)@e;t=(points-a)@n;thickness={}
    for fraction in (.05,.1,.25,.5,.75,.9,.95):
        q=fraction*chord;cross=[]
        for k in range(len(points)-1):
            if (s[k]<=q<s[k+1]) or (s[k+1]<=q<s[k]):cross.append(float(t[k]+(t[k+1]-t[k])*(q-s[k])/(s[k+1]-s[k])))
        thickness[str(fraction)]=max(cross)-min(cross) if len(cross)>=2 else None
    return {'z_mm':z_mm,'closed_loops':len(loops),'section_points':len(cloud),'diameter_chord_proxy_mm':chord,'diameter_orientation_proxy_deg':math.degrees(math.atan2(e[1],e[0])),'normal_section_thickness_mm':thickness,'not_designed_airfoil_chord_or_twist':True}


def compare_sections(source,adapted,output_json):
    import vtk
    polys=[]
    for path in (source,adapted):
        reader=vtk.vtkSTLReader();reader.SetFileName(str(path));reader.Update();poly=vtk.vtkPolyData();poly.DeepCopy(reader.GetOutput());polys.append(poly)
    rows=[]
    for z in (-145.,-125.,-100.,-75.,-50.,-30.,30.,50.,75.,100.,125.,145.):
        a=section(polys[0],z);b=section(polys[1],z);changes={}
        for key,value in a['normal_section_thickness_mm'].items():
            other=b['normal_section_thickness_mm'][key];changes[key]=(other/value-1) if value and other is not None else None
        rows.append({'source':a,'adapted':b,'chord_change_fraction':b['diameter_chord_proxy_mm']/a['diameter_chord_proxy_mm']-1,'orientation_change_deg':b['diameter_orientation_proxy_deg']-a['diameter_orientation_proxy_deg'],'thickness_change_fraction':changes})
    result={'geometry_only':True,'airfoil_or_aerodynamic_qualification':False,'source':str(source),'adapted':str(adapted),'sections':rows,'maximum_chord_change_fraction':max(abs(r['chord_change_fraction']) for r in rows),'maximum_orientation_change_deg':max(abs(r['orientation_change_deg']) for r in rows),'maximum_thickness_change_fraction':max(abs(v) for r in rows for v in r['thickness_change_fraction'].values() if v is not None)}
    Path(output_json).write_text(json.dumps(result,indent=2)+'\n');return result
