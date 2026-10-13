# SPDX-License-Identifier: Apache-2.0
"""Contained optional native VTK point preview; no interpolation or physics."""
import json
import math
from pathlib import Path
import sys

def preview(path):
    try:
        from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader
    except ImportError:
        return {'status':'reader_unavailable','message':'Install VTK into the SPIKE worker Python environment for native field previews.'}
    reader=vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    if reader.GetErrorCode():
        return {'status':'failed','message':'Native VTK reader rejected the field file.'}
    grid=reader.GetOutput()
    count=grid.GetNumberOfPoints()
    if count<1:
        return {'status':'unsupported','message':'No unstructured-grid points were returned.'}
    indices=list(range(count)) if count<=2000 else [i*(count-1)//1999 for i in range(2000)]
    coordinates=[list(grid.GetPoint(i)) for i in indices]
    if any(not all(math.isfinite(v) for v in point) for point in coordinates):
        return {'status':'failed','message':'Nonfinite native mesh coordinates.'}
    arrays=[]
    data=grid.GetPointData()
    units={'E':'V/m','E_real':'V/m','E_imag':'V/m','B':'T','B_real':'T','B_imag':'T'}
    omissions=[]
    for n in range(data.GetNumberOfArrays()):
        array=data.GetArray(n)
        if array is None:
            continue
        name=array.GetName() or ('array-'+str(n))
        components=array.GetNumberOfComponents()
        if len(arrays)>=16 or components<1 or components>9 or array.GetNumberOfTuples()!=count:
            omissions.append(name)
            continue
        values=[list(array.GetTuple(i)) for i in indices]
        if any(not all(math.isfinite(v) for v in row) for row in values):
            omissions.append(name)
            continue
        arrays.append({'name':name,'components':components,'values':values,'units':units.get(name)})
    return {'status':'available','points':coordinates,'source_point_count':count,'sampled':count>2000,
            'arrays':arrays,'omitted_arrays':omissions,'preview_kind':'native_point_cloud'}

if __name__=='__main__':
    print(json.dumps(preview(Path(sys.argv[1])),allow_nan=False,separators=(',',':')))
