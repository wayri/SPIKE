#define _USE_MATH_DEFINES
#include <cmath>
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/complex.h>
#include <nanobind/stl/function.h>
#include <nanobind/stl/array.h>

// Eigen integration for nanobind is needed to pass matrices,
// but for now we bind the interface without direct dense matrix return types
// or we use nanobind's ndarray to cast from Eigen.
#include <nanobind/ndarray.h>
#include <nanobind/eigen/dense.h>
#include <nanobind/eigen/sparse.h>

#include "geometry/planar_topology.hpp"
#include "peec/peec_solver.hpp"
#include "peec/volume_matrix.hpp"
#include "peec/reference_plane_antipad_mesh_input.hpp"
#include "peec/generalized_reference_plane_mesh_input.hpp"
#include "peec/via_transition_mesh_input.hpp"
#include "thermal/thermal_solver.hpp"

namespace nb = nanobind;
using namespace nb::literals;

NB_MODULE(spike_peec_native, m) {
    m.doc() = "SPIKE Simulation Engine C++ Backend bindings";

    namespace volume = spike::peec::volume;
    nb::class_<volume::RectangularVolume>(m, "VolumeRectangularBasis")
        .def(nb::init<>())
        .def_rw("center_m", &volume::RectangularVolume::center_m)
        .def_rw("direction", &volume::RectangularVolume::direction)
        .def_rw("width_axis", &volume::RectangularVolume::width_axis)
        .def_rw("length_m", &volume::RectangularVolume::length_m)
        .def_rw("width_m", &volume::RectangularVolume::width_m)
        .def_rw("thickness_m", &volume::RectangularVolume::thickness_m);
    nb::class_<volume::CoaxialAnnulusVolume>(m, "VolumeCoaxialAnnulusBasis")
        .def(nb::init<>())
        .def_rw("center_m", &volume::CoaxialAnnulusVolume::center_m)
        .def_rw("direction", &volume::CoaxialAnnulusVolume::direction)
        .def_rw("length_m", &volume::CoaxialAnnulusVolume::length_m)
        .def_rw("inner_radius_m", &volume::CoaxialAnnulusVolume::inner_radius_m)
        .def_rw("outer_radius_m", &volume::CoaxialAnnulusVolume::outer_radius_m);
    nb::class_<volume::IntegrationOptions>(m, "VolumePairIntegrationOptions")
        .def(nb::init<>())
        .def_rw("relative_tolerance", &volume::IntegrationOptions::relative_tolerance)
        .def_rw("absolute_tolerance_h", &volume::IntegrationOptions::absolute_tolerance_h)
        .def_rw("max_potential_evaluations", &volume::IntegrationOptions::max_potential_evaluations)
        .def_rw("max_cells", &volume::IntegrationOptions::max_cells)
        .def_rw("permeability_h_per_m", &volume::IntegrationOptions::permeability_h_per_m);
    nb::class_<volume::AnnularIntegrationOptions>(m, "VolumeAnnularIntegrationOptions")
        .def(nb::init<>())
        .def_rw("relative_tolerance", &volume::AnnularIntegrationOptions::relative_tolerance)
        .def_rw("absolute_tolerance_h", &volume::AnnularIntegrationOptions::absolute_tolerance_h)
        .def_rw("max_evaluations", &volume::AnnularIntegrationOptions::max_evaluations)
        .def_rw("max_cells", &volume::AnnularIntegrationOptions::max_cells)
        .def_rw("permeability_h_per_m", &volume::AnnularIntegrationOptions::permeability_h_per_m);
    nb::class_<volume::MatrixIntegrationOptions>(m, "VolumeMatrixIntegrationOptions")
        .def(nb::init<>())
        .def_rw("pair", &volume::MatrixIntegrationOptions::pair)
        .def_rw("annular_pair", &volume::MatrixIntegrationOptions::annular_pair)
        .def_rw("maximum_matrix_pairs", &volume::MatrixIntegrationOptions::maximum_matrix_pairs)
        .def_rw("maximum_total_potential_evaluations", &volume::MatrixIntegrationOptions::maximum_total_potential_evaluations);
    nb::class_<volume::MatrixIntegrationResult>(m, "VolumeMatrixResult")
        .def_ro("inductance_h", &volume::MatrixIntegrationResult::inductance_h)
        .def_ro("estimated_error_h", &volume::MatrixIntegrationResult::estimated_error_h)
        .def_ro("reciprocity_difference_h", &volume::MatrixIntegrationResult::reciprocity_difference_h)
        .def_ro("potential_evaluations", &volume::MatrixIntegrationResult::potential_evaluations)
        .def_ro("pair_count", &volume::MatrixIntegrationResult::pair_count)
        .def_ro("converged", &volume::MatrixIntegrationResult::converged)
        .def_ro("failure_code", &volume::MatrixIntegrationResult::failure_code)
        .def_ro("failure_pair_i", &volume::MatrixIntegrationResult::failure_pair_i)
        .def_ro("failure_pair_j", &volume::MatrixIntegrationResult::failure_pair_j);
    nb::class_<volume::VolumeMatrixAssembler>(m, "VolumeMatrixAssembler")
        .def(nb::init<volume::MatrixIntegrationOptions>(), nb::arg("options") = volume::MatrixIntegrationOptions())
        .def("add_rectangular", &volume::VolumeMatrixAssembler::add_rectangular)
        .def("add_coaxial_annulus", &volume::VolumeMatrixAssembler::add_coaxial_annulus)
        .def("basis_count", &volume::VolumeMatrixAssembler::basis_count)
        .def("clear", &volume::VolumeMatrixAssembler::clear)
        .def("compute_inductance", &volume::VolumeMatrixAssembler::compute_inductance);

    nb::class_<spike::geometry::Point2>(m, "PlanarPoint2")
        .def(nb::init<>())
        .def_rw("x", &spike::geometry::Point2::x)
        .def_rw("y", &spike::geometry::Point2::y);
    nb::class_<spike::geometry::CanonicalRing>(m, "CanonicalPlanarRing")
        .def_ro("points", &spike::geometry::CanonicalRing::points)
        .def_ro("signed_area", &spike::geometry::CanonicalRing::signed_area)
        .def_ro("input_reversed", &spike::geometry::CanonicalRing::input_reversed)
        .def_ro("simple", &spike::geometry::CanonicalRing::simple);
    nb::class_<spike::geometry::QuantizedPoint2>(m, "QuantizedPlanarPoint2")
        .def(nb::init<>())
        .def_rw("x", &spike::geometry::QuantizedPoint2::x)
        .def_rw("y", &spike::geometry::QuantizedPoint2::y);
    nb::class_<spike::geometry::CanonicalQuantizedRing>(m, "CanonicalQuantizedRing")
        .def_ro("points", &spike::geometry::CanonicalQuantizedRing::points)
        .def_ro("area_mm2", &spike::geometry::CanonicalQuantizedRing::area_mm2)
        .def_ro("input_reversed", &spike::geometry::CanonicalQuantizedRing::input_reversed)
        .def_ro("simple", &spike::geometry::CanonicalQuantizedRing::simple);
    nb::class_<spike::geometry::CanonicalPlanarRegion>(m, "CanonicalPlanarRegion")
        .def_ro("outer", &spike::geometry::CanonicalPlanarRegion::outer)
        .def_ro("cutouts", &spike::geometry::CanonicalPlanarRegion::cutouts)
        .def_ro("copper_area_mm2", &spike::geometry::CanonicalPlanarRegion::copper_area_mm2)
        .def_ro("coordinate_grid_mm", &spike::geometry::CanonicalPlanarRegion::coordinate_grid_mm)
        .def_ro("topology_valid", &spike::geometry::CanonicalPlanarRegion::topology_valid);
    nb::class_<spike::geometry::QuantizedTriangle>(m, "QuantizedPlanarTriangle")
        .def_ro("a", &spike::geometry::QuantizedTriangle::a)
        .def_ro("b", &spike::geometry::QuantizedTriangle::b)
        .def_ro("c", &spike::geometry::QuantizedTriangle::c);
    nb::class_<spike::geometry::SimplePlanarTriangulation>(m, "SimplePlanarTriangulation")
        .def_ro("vertices", &spike::geometry::SimplePlanarTriangulation::vertices)
        .def_ro("triangles", &spike::geometry::SimplePlanarTriangulation::triangles)
        .def_ro("twice_area_grid", &spike::geometry::SimplePlanarTriangulation::twice_area_grid)
        .def_ro("work_steps", &spike::geometry::SimplePlanarTriangulation::work_steps)
        .def_ro("boundary_constraints_preserved",
                &spike::geometry::SimplePlanarTriangulation::boundary_constraints_preserved)
        .def_ro("exact_area_preserved", &spike::geometry::SimplePlanarTriangulation::exact_area_preserved);
    nb::class_<spike::geometry::ConstrainedPlanarTriangulation>(
        m, "ConstrainedPlanarTriangulation")
        .def_ro("vertices", &spike::geometry::ConstrainedPlanarTriangulation::vertices)
        .def_ro("triangles", &spike::geometry::ConstrainedPlanarTriangulation::triangles)
        .def_ro("boundary_loops", &spike::geometry::ConstrainedPlanarTriangulation::boundary_loops)
        .def_ro("twice_area_grid", &spike::geometry::ConstrainedPlanarTriangulation::twice_area_grid)
        .def_ro("work_steps", &spike::geometry::ConstrainedPlanarTriangulation::work_steps)
        .def_ro("boundary_constraints_preserved",
                &spike::geometry::ConstrainedPlanarTriangulation::boundary_constraints_preserved)
        .def_ro("exact_area_preserved",
                &spike::geometry::ConstrainedPlanarTriangulation::exact_area_preserved)
        .def_ro("domain_classified",
                &spike::geometry::ConstrainedPlanarTriangulation::domain_classified)
        .def_ro("locally_delaunay",
                &spike::geometry::ConstrainedPlanarTriangulation::locally_delaunay);
    m.def("certified_planar_orientation", &spike::geometry::certified_orientation);
    m.def("exact_quantized_planar_orientation", &spike::geometry::exact_quantized_orientation);
    m.def("exact_quantized_planar_incircle", &spike::geometry::exact_quantized_incircle);
    m.def("exact_quantized_planar_orientation_scaled",
          &spike::geometry::exact_quantized_orientation_scaled);
    m.def("exact_quantized_planar_twice_area", &spike::geometry::exact_quantized_twice_area);
    m.def("canonicalize_simple_planar_ring", &spike::geometry::canonicalize_simple_ring,
          nb::arg("points"), nb::arg("maximum_points") = 4096);
    m.def("canonicalize_planar_region", &spike::geometry::canonicalize_planar_region,
          nb::arg("outer"), nb::arg("cutouts"),
          nb::arg("coordinate_grid_mm") = 0.000001,
          nb::arg("maximum_total_points") = 16384);
    m.def("triangulate_simple_planar_ring", &spike::geometry::triangulate_simple_planar_ring,
          nb::arg("ring"), nb::arg("maximum_points") = 4096,
          nb::arg("maximum_triangles") = 8192,
          nb::arg("maximum_work_steps") = 16777216);
    m.def("triangulate_constrained_planar_region",
          [](const spike::geometry::CanonicalPlanarRegion &region,
             std::size_t maximum_vertices, std::size_t maximum_holes,
             std::size_t maximum_triangles, std::size_t maximum_work_steps,
             nb::object cancel_check) {
              std::function<bool()> cancellation_requested;
              if (!cancel_check.is_none())
                  cancellation_requested = [cancel_check]() {
                      return nb::cast<bool>(cancel_check());
                  };
              return spike::geometry::triangulate_constrained_planar_region(
                  region, maximum_vertices, maximum_holes, maximum_triangles,
                  maximum_work_steps, cancellation_requested);
          },
          nb::arg("region"), nb::arg("maximum_vertices") = 4096,
          nb::arg("maximum_holes") = 128,
          nb::arg("maximum_triangles") = 8192,
          nb::arg("maximum_work_steps") = 16777216,
          nb::arg("cancel_check") = nb::none());

    // Solver-independent geometry admission. These input records are mutable
    // only so Python can construct the typed boundary; the returned evidence
    // is immutable and cannot invoke a physics solver.
    nb::class_<spike::peec::ViaTransitionVertex>(m, "ViaTransitionVertex")
        .def(nb::init<>())
        .def_rw("x", &spike::peec::ViaTransitionVertex::x)
        .def_rw("y", &spike::peec::ViaTransitionVertex::y)
        .def_rw("z", &spike::peec::ViaTransitionVertex::z);

    nb::class_<spike::peec::ViaTransitionTriangle>(m, "ViaTransitionTriangle")
        .def(nb::init<>())
        .def_rw("id", &spike::peec::ViaTransitionTriangle::id)
        .def_rw("a", &spike::peec::ViaTransitionTriangle::a)
        .def_rw("b", &spike::peec::ViaTransitionTriangle::b)
        .def_rw("c", &spike::peec::ViaTransitionTriangle::c)
        .def_rw("domain_index", &spike::peec::ViaTransitionTriangle::domain_index)
        .def_rw("surface_role", &spike::peec::ViaTransitionTriangle::surface_role)
        .def_rw("source_ids", &spike::peec::ViaTransitionTriangle::source_ids);

    nb::class_<spike::peec::ViaTransitionDomain>(m, "ViaTransitionDomain")
        .def(nb::init<>())
        .def_rw("id", &spike::peec::ViaTransitionDomain::id)
        .def_rw("kind", &spike::peec::ViaTransitionDomain::kind)
        .def_rw("net_id", &spike::peec::ViaTransitionDomain::net_id)
        .def_rw("layer_ids", &spike::peec::ViaTransitionDomain::layer_ids)
        .def_rw("source_ids", &spike::peec::ViaTransitionDomain::source_ids);

    nb::class_<spike::peec::ViaTransitionMeshInput>(m, "ViaTransitionMeshInput")
        .def(nb::init<>())
        .def_rw("contract", &spike::peec::ViaTransitionMeshInput::contract)
        .def_rw("source_geometry_contract", &spike::peec::ViaTransitionMeshInput::source_geometry_contract)
        .def_rw("source_geometry_sha256", &spike::peec::ViaTransitionMeshInput::source_geometry_sha256)
        .def_rw("design_id", &spike::peec::ViaTransitionMeshInput::design_id)
        .def_rw("via_id", &spike::peec::ViaTransitionMeshInput::via_id)
        .def_rw("source_via_id", &spike::peec::ViaTransitionMeshInput::source_via_id)
        .def_rw("vertices", &spike::peec::ViaTransitionMeshInput::vertices)
        .def_rw("triangles", &spike::peec::ViaTransitionMeshInput::triangles)
        .def_rw("domains", &spike::peec::ViaTransitionMeshInput::domains)
        .def_rw("declared_vertex_count", &spike::peec::ViaTransitionMeshInput::declared_vertex_count)
        .def_rw("declared_triangle_count", &spike::peec::ViaTransitionMeshInput::declared_triangle_count)
        .def_rw("declared_domain_count", &spike::peec::ViaTransitionMeshInput::declared_domain_count)
        .def_rw("solver_ready", &spike::peec::ViaTransitionMeshInput::solver_ready);

    nb::class_<spike::peec::ViaTransitionMeshValidation>(m, "ViaTransitionMeshValidation")
        .def_ro("contract", &spike::peec::ViaTransitionMeshValidation::contract)
        .def_ro("source_geometry_contract", &spike::peec::ViaTransitionMeshValidation::source_geometry_contract)
        .def_ro("source_geometry_sha256", &spike::peec::ViaTransitionMeshValidation::source_geometry_sha256)
        .def_ro("vertex_count", &spike::peec::ViaTransitionMeshValidation::vertex_count)
        .def_ro("triangle_count", &spike::peec::ViaTransitionMeshValidation::triangle_count)
        .def_ro("domain_count", &spike::peec::ViaTransitionMeshValidation::domain_count)
        .def_ro("finite_geometry", &spike::peec::ViaTransitionMeshValidation::finite_geometry)
        .def_ro("compact_indexing", &spike::peec::ViaTransitionMeshValidation::compact_indexing)
        .def_ro("closed_oriented_domains", &spike::peec::ViaTransitionMeshValidation::closed_oriented_domains)
        .def_ro("provenance_retained", &spike::peec::ViaTransitionMeshValidation::provenance_retained)
        .def_ro("solver_ready", &spike::peec::ViaTransitionMeshValidation::solver_ready);

    m.def("validate_via_transition_mesh_input",
          &spike::peec::validate_via_transition_mesh_input,
          nb::arg("input"), nb::arg("expected_geometry_sha256"));

    nb::class_<spike::peec::ReferencePlaneAntipadVertex>(m, "ReferencePlaneAntipadVertex")
        .def(nb::init<>())
        .def_rw("x", &spike::peec::ReferencePlaneAntipadVertex::x)
        .def_rw("y", &spike::peec::ReferencePlaneAntipadVertex::y)
        .def_rw("z", &spike::peec::ReferencePlaneAntipadVertex::z);
    nb::class_<spike::peec::ReferencePlaneAntipadTriangle>(m, "ReferencePlaneAntipadTriangle")
        .def(nb::init<>())
        .def_rw("id", &spike::peec::ReferencePlaneAntipadTriangle::id)
        .def_rw("a", &spike::peec::ReferencePlaneAntipadTriangle::a)
        .def_rw("b", &spike::peec::ReferencePlaneAntipadTriangle::b)
        .def_rw("c", &spike::peec::ReferencePlaneAntipadTriangle::c)
        .def_rw("domain_index", &spike::peec::ReferencePlaneAntipadTriangle::domain_index)
        .def_rw("surface_role", &spike::peec::ReferencePlaneAntipadTriangle::surface_role)
        .def_rw("source_ids", &spike::peec::ReferencePlaneAntipadTriangle::source_ids);
    nb::class_<spike::peec::ReferencePlaneAntipadDomain>(m, "ReferencePlaneAntipadDomain")
        .def(nb::init<>())
        .def_rw("id", &spike::peec::ReferencePlaneAntipadDomain::id)
        .def_rw("net_id", &spike::peec::ReferencePlaneAntipadDomain::net_id)
        .def_rw("layer_id", &spike::peec::ReferencePlaneAntipadDomain::layer_id)
        .def_rw("source_ids", &spike::peec::ReferencePlaneAntipadDomain::source_ids)
        .def_rw("reference_zone_id", &spike::peec::ReferencePlaneAntipadDomain::reference_zone_id)
        .def_rw("source_zone_sha256", &spike::peec::ReferencePlaneAntipadDomain::source_zone_sha256)
        .def_rw("resolved_region_sha256", &spike::peec::ReferencePlaneAntipadDomain::resolved_region_sha256)
        .def_rw("antipad_radius_mm", &spike::peec::ReferencePlaneAntipadDomain::antipad_radius_mm);
    nb::class_<spike::peec::ReferencePlaneAntipadMeshInput>(m, "ReferencePlaneAntipadMeshInput")
        .def(nb::init<>())
        .def_rw("contract", &spike::peec::ReferencePlaneAntipadMeshInput::contract)
        .def_rw("source_geometry_contract", &spike::peec::ReferencePlaneAntipadMeshInput::source_geometry_contract)
        .def_rw("source_geometry_sha256", &spike::peec::ReferencePlaneAntipadMeshInput::source_geometry_sha256)
        .def_rw("design_id", &spike::peec::ReferencePlaneAntipadMeshInput::design_id)
        .def_rw("via_id", &spike::peec::ReferencePlaneAntipadMeshInput::via_id)
        .def_rw("source_via_id", &spike::peec::ReferencePlaneAntipadMeshInput::source_via_id)
        .def_rw("vertices", &spike::peec::ReferencePlaneAntipadMeshInput::vertices)
        .def_rw("triangles", &spike::peec::ReferencePlaneAntipadMeshInput::triangles)
        .def_rw("domains", &spike::peec::ReferencePlaneAntipadMeshInput::domains)
        .def_rw("declared_vertex_count", &spike::peec::ReferencePlaneAntipadMeshInput::declared_vertex_count)
        .def_rw("declared_triangle_count", &spike::peec::ReferencePlaneAntipadMeshInput::declared_triangle_count)
        .def_rw("declared_domain_count", &spike::peec::ReferencePlaneAntipadMeshInput::declared_domain_count)
        .def_rw("solver_ready", &spike::peec::ReferencePlaneAntipadMeshInput::solver_ready);
    nb::class_<spike::peec::ReferencePlaneAntipadMeshValidation>(m, "ReferencePlaneAntipadMeshValidation")
        .def_ro("contract", &spike::peec::ReferencePlaneAntipadMeshValidation::contract)
        .def_ro("source_geometry_contract", &spike::peec::ReferencePlaneAntipadMeshValidation::source_geometry_contract)
        .def_ro("source_geometry_sha256", &spike::peec::ReferencePlaneAntipadMeshValidation::source_geometry_sha256)
        .def_ro("vertex_count", &spike::peec::ReferencePlaneAntipadMeshValidation::vertex_count)
        .def_ro("triangle_count", &spike::peec::ReferencePlaneAntipadMeshValidation::triangle_count)
        .def_ro("domain_count", &spike::peec::ReferencePlaneAntipadMeshValidation::domain_count)
        .def_ro("finite_geometry", &spike::peec::ReferencePlaneAntipadMeshValidation::finite_geometry)
        .def_ro("compact_indexing", &spike::peec::ReferencePlaneAntipadMeshValidation::compact_indexing)
        .def_ro("closed_oriented_domains", &spike::peec::ReferencePlaneAntipadMeshValidation::closed_oriented_domains)
        .def_ro("provenance_retained", &spike::peec::ReferencePlaneAntipadMeshValidation::provenance_retained)
        .def_ro("solver_ready", &spike::peec::ReferencePlaneAntipadMeshValidation::solver_ready);
    m.def("validate_reference_plane_antipad_mesh_input",
          &spike::peec::validate_reference_plane_antipad_mesh_input,
          nb::arg("input"), nb::arg("expected_geometry_sha256"));

    nb::class_<spike::peec::GeneralizedReferencePlaneVertex>(m, "GeneralizedReferencePlaneVertex")
        .def(nb::init<>()).def_rw("x", &spike::peec::GeneralizedReferencePlaneVertex::x)
        .def_rw("y", &spike::peec::GeneralizedReferencePlaneVertex::y)
        .def_rw("z", &spike::peec::GeneralizedReferencePlaneVertex::z);
    nb::class_<spike::peec::GeneralizedReferencePlaneTriangle>(m, "GeneralizedReferencePlaneTriangle")
        .def(nb::init<>()).def_rw("id", &spike::peec::GeneralizedReferencePlaneTriangle::id)
        .def_rw("a", &spike::peec::GeneralizedReferencePlaneTriangle::a)
        .def_rw("b", &spike::peec::GeneralizedReferencePlaneTriangle::b)
        .def_rw("c", &spike::peec::GeneralizedReferencePlaneTriangle::c)
        .def_rw("domain_index", &spike::peec::GeneralizedReferencePlaneTriangle::domain_index)
        .def_rw("surface_role", &spike::peec::GeneralizedReferencePlaneTriangle::surface_role)
        .def_rw("source_ids", &spike::peec::GeneralizedReferencePlaneTriangle::source_ids);
    nb::class_<spike::peec::GeneralizedReferencePlaneDomain>(m, "GeneralizedReferencePlaneDomain")
        .def(nb::init<>()).def_rw("id", &spike::peec::GeneralizedReferencePlaneDomain::id)
        .def_rw("net_id", &spike::peec::GeneralizedReferencePlaneDomain::net_id)
        .def_rw("layer_id", &spike::peec::GeneralizedReferencePlaneDomain::layer_id)
        .def_rw("source_ids", &spike::peec::GeneralizedReferencePlaneDomain::source_ids)
        .def_rw("reference_zone_id", &spike::peec::GeneralizedReferencePlaneDomain::reference_zone_id)
        .def_rw("source_zone_sha256", &spike::peec::GeneralizedReferencePlaneDomain::source_zone_sha256)
        .def_rw("resolved_region_sha256", &spike::peec::GeneralizedReferencePlaneDomain::resolved_region_sha256)
        .def_rw("source_boundary_sha256", &spike::peec::GeneralizedReferencePlaneDomain::source_boundary_sha256)
        .def_rw("flattened_boundary_sha256", &spike::peec::GeneralizedReferencePlaneDomain::flattened_boundary_sha256)
        .def_rw("antipad_radius_mm", &spike::peec::GeneralizedReferencePlaneDomain::antipad_radius_mm)
        .def_rw("exact_discrete_area_mm2", &spike::peec::GeneralizedReferencePlaneDomain::exact_discrete_area_mm2)
        .def_rw("exact_discrete_volume_mm3", &spike::peec::GeneralizedReferencePlaneDomain::exact_discrete_volume_mm3)
        .def_rw("source_cutout_count", &spike::peec::GeneralizedReferencePlaneDomain::source_cutout_count);
    nb::class_<spike::peec::GeneralizedReferencePlaneLoop>(m, "GeneralizedReferencePlaneLoop")
        .def(nb::init<>()).def_rw("id", &spike::peec::GeneralizedReferencePlaneLoop::id)
        .def_rw("domain_index", &spike::peec::GeneralizedReferencePlaneLoop::domain_index)
        .def_rw("role", &spike::peec::GeneralizedReferencePlaneLoop::role)
        .def_rw("surface", &spike::peec::GeneralizedReferencePlaneLoop::surface)
        .def_rw("z_mm", &spike::peec::GeneralizedReferencePlaneLoop::z_mm)
        .def_rw("vertex_indices", &spike::peec::GeneralizedReferencePlaneLoop::vertex_indices)
        .def_rw("source_ids", &spike::peec::GeneralizedReferencePlaneLoop::source_ids);
    nb::class_<spike::peec::GeneralizedReferencePlaneMeshInput>(m, "GeneralizedReferencePlaneMeshInput")
        .def(nb::init<>()).def_rw("contract", &spike::peec::GeneralizedReferencePlaneMeshInput::contract)
        .def_rw("source_geometry_contract", &spike::peec::GeneralizedReferencePlaneMeshInput::source_geometry_contract)
        .def_rw("source_geometry_sha256", &spike::peec::GeneralizedReferencePlaneMeshInput::source_geometry_sha256)
        .def_rw("design_id", &spike::peec::GeneralizedReferencePlaneMeshInput::design_id)
        .def_rw("via_id", &spike::peec::GeneralizedReferencePlaneMeshInput::via_id)
        .def_rw("source_via_id", &spike::peec::GeneralizedReferencePlaneMeshInput::source_via_id)
        .def_rw("vertices", &spike::peec::GeneralizedReferencePlaneMeshInput::vertices)
        .def_rw("triangles", &spike::peec::GeneralizedReferencePlaneMeshInput::triangles)
        .def_rw("domains", &spike::peec::GeneralizedReferencePlaneMeshInput::domains)
        .def_rw("loops", &spike::peec::GeneralizedReferencePlaneMeshInput::loops)
        .def_rw("declared_vertex_count", &spike::peec::GeneralizedReferencePlaneMeshInput::declared_vertex_count)
        .def_rw("declared_triangle_count", &spike::peec::GeneralizedReferencePlaneMeshInput::declared_triangle_count)
        .def_rw("declared_domain_count", &spike::peec::GeneralizedReferencePlaneMeshInput::declared_domain_count)
        .def_rw("declared_loop_count", &spike::peec::GeneralizedReferencePlaneMeshInput::declared_loop_count)
        .def_rw("maximum_work_steps", &spike::peec::GeneralizedReferencePlaneMeshInput::maximum_work_steps)
        .def_rw("actual_work_steps", &spike::peec::GeneralizedReferencePlaneMeshInput::actual_work_steps)
        .def_rw("mesh_topology_admitted", &spike::peec::GeneralizedReferencePlaneMeshInput::mesh_topology_admitted)
        .def_rw("conservative_source_copper_envelope_proven", &spike::peec::GeneralizedReferencePlaneMeshInput::conservative_source_copper_envelope_proven)
        .def_rw("native_handoff_ready", &spike::peec::GeneralizedReferencePlaneMeshInput::native_handoff_ready)
        .def_rw("mesh_quality_performed", &spike::peec::GeneralizedReferencePlaneMeshInput::mesh_quality_performed)
        .def_rw("solver_ready", &spike::peec::GeneralizedReferencePlaneMeshInput::solver_ready);
    nb::class_<spike::peec::GeneralizedReferencePlaneMeshValidation>(m, "GeneralizedReferencePlaneMeshValidation")
        .def_ro("contract", &spike::peec::GeneralizedReferencePlaneMeshValidation::contract)
        .def_ro("source_geometry_contract", &spike::peec::GeneralizedReferencePlaneMeshValidation::source_geometry_contract)
        .def_ro("source_geometry_sha256", &spike::peec::GeneralizedReferencePlaneMeshValidation::source_geometry_sha256)
        .def_ro("vertex_count", &spike::peec::GeneralizedReferencePlaneMeshValidation::vertex_count)
        .def_ro("triangle_count", &spike::peec::GeneralizedReferencePlaneMeshValidation::triangle_count)
        .def_ro("domain_count", &spike::peec::GeneralizedReferencePlaneMeshValidation::domain_count)
        .def_ro("loop_count", &spike::peec::GeneralizedReferencePlaneMeshValidation::loop_count)
        .def_ro("finite_geometry", &spike::peec::GeneralizedReferencePlaneMeshValidation::finite_geometry)
        .def_ro("compact_indexing", &spike::peec::GeneralizedReferencePlaneMeshValidation::compact_indexing)
        .def_ro("closed_oriented_domains", &spike::peec::GeneralizedReferencePlaneMeshValidation::closed_oriented_domains)
        .def_ro("provenance_retained", &spike::peec::GeneralizedReferencePlaneMeshValidation::provenance_retained)
        .def_ro("complete_loop_coverage", &spike::peec::GeneralizedReferencePlaneMeshValidation::complete_loop_coverage)
        .def_ro("complete_surface_roles", &spike::peec::GeneralizedReferencePlaneMeshValidation::complete_surface_roles)
        .def_ro("source_curve_claim_honest", &spike::peec::GeneralizedReferencePlaneMeshValidation::source_curve_claim_honest)
        .def_ro("solver_ready", &spike::peec::GeneralizedReferencePlaneMeshValidation::solver_ready);
    m.def("validate_generalized_reference_plane_mesh_input",
          &spike::peec::validate_generalized_reference_plane_mesh_input,
          nb::arg("input"), nb::arg("expected_geometry_sha256"));

    // Bind Point3D
    nb::class_<spike::peec::Point3D>(m, "Point3D")
        .def(nb::init<>())
        .def(nb::init<double, double, double>())
        .def_rw("x", &spike::peec::Point3D::x)
        .def_rw("y", &spike::peec::Point3D::y)
        .def_rw("z", &spike::peec::Point3D::z)
        .def("norm", &spike::peec::Point3D::norm);

    // Bind Filament
    nb::class_<spike::peec::Filament>(m, "Filament")
        .def(nb::init<>())
        .def_rw("start", &spike::peec::Filament::start)
        .def_rw("end", &spike::peec::Filament::end)
        .def_rw("width", &spike::peec::Filament::width)
        .def_rw("thickness", &spike::peec::Filament::thickness)
        .def_rw("node_p", &spike::peec::Filament::node_p)
        .def_rw("node_n", &spike::peec::Filament::node_n)
        .def_rw("conductivity", &spike::peec::Filament::conductivity)
        .def("length", &spike::peec::Filament::length)
        .def("area", &spike::peec::Filament::area)
        .def("resistance", &spike::peec::Filament::resistance);

    // Bind SolverType
    nb::enum_<spike::peec::SolverType>(m, "SolverType")
        .value("DENSE_DIRECT", spike::peec::SolverType::DENSE_DIRECT)
        .value("SPARSE_ITERATIVE", spike::peec::SolverType::SPARSE_ITERATIVE)
        .export_values();

    // Bind PEECConfig
    nb::class_<spike::peec::PEECConfig>(m, "PEECConfig")
        .def(nb::init<>())
        .def_rw("mu_0", &spike::peec::PEECConfig::mu_0)
        .def_rw("eps_0", &spike::peec::PEECConfig::eps_0)
        .def_rw("eps_r", &spike::peec::PEECConfig::eps_r)
        .def_rw("quad_order", &spike::peec::PEECConfig::quad_order)
        .def_rw("use_analytic_singular", &spike::peec::PEECConfig::use_analytic_singular)
        .def_rw("num_threads", &spike::peec::PEECConfig::num_threads)
        .def_rw("enable_skin_effect", &spike::peec::PEECConfig::enable_skin_effect)
        .def_rw("enable_hammerstad_roughness", &spike::peec::PEECConfig::enable_hammerstad_roughness)
        .def_rw("roughness_rms_um", &spike::peec::PEECConfig::roughness_rms_um)
        .def_rw("solver_type", &spike::peec::PEECConfig::solver_type)
        .def_rw("sparse_threshold", &spike::peec::PEECConfig::sparse_threshold);

    // Bind PEECSolver
    nb::class_<spike::peec::PEECSolver>(m, "PEECSolver")
        .def(nb::init<const spike::peec::PEECConfig&>(), nb::arg("config") = spike::peec::PEECConfig())
        .def("add_filament", &spike::peec::PEECSolver::add_filament)
        .def("compute_partial_inductance", &spike::peec::PEECSolver::compute_partial_inductance)
        .def("compute_resistance", &spike::peec::PEECSolver::compute_resistance, nb::arg("frequency") = 0.0)
        .def("compute_capacitance", &spike::peec::PEECSolver::compute_capacitance)
        .def("solve_frequency", &spike::peec::PEECSolver::solve_frequency)
        .def("num_filaments", &spike::peec::PEECSolver::num_filaments)
        .def("clear", &spike::peec::PEECSolver::clear);
}
