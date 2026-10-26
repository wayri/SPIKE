# SPDX-License-Identifier: Apache-2.0
"""Optional native geometry-screen oracles, no CFD qualification claims."""
import importlib.util
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_coarsen import _point_to_triangle_upper, _continuous_distance_bound

class GeometryBounds(unittest.TestCase):
 def test_explicit_convex_candidate_distance_upper(self):
  target=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
  points=np.array([[.2,.2,2.],[-1.,0.,0.],[1.,1.,0.]])
  np.testing.assert_allclose(_point_to_triangle_upper(points,target),[2.,1.,np.sqrt(.5)],rtol=1e-12,atol=1e-12)
 @unittest.skipUnless(importlib.util.find_spec('vtk'),'Optional installed VTK geometry tool unavailable')
 def test_continuous_cover_accepts_and_rejects_translated_surface(self):
  import vtk
  a=vtk.vtkCubeSource();a.SetBounds(0,1,0,1,0,1);a.Update();ta=vtk.vtkTriangleFilter();ta.SetInputConnection(a.GetOutputPort());ta.Update()
  b=vtk.vtkCubeSource();b.SetBounds(0,1,0,1,.05,1.05);b.Update();tb=vtk.vtkTriangleFilter();tb.SetInputConnection(b.GetOutputPort());tb.Update()
  self.assertTrue(_continuous_distance_bound(ta.GetOutput(),tb.GetOutput(),.1,max_queries=10000)['passed'])
  self.assertFalse(_continuous_distance_bound(ta.GetOutput(),tb.GetOutput(),.01,max_queries=10000)['passed'])

if __name__=='__main__':unittest.main()
