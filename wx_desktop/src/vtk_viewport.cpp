#include "spike_wx/vtk_viewport.hpp"

#include <wx/dcclient.h>
#include <wx/toplevel.h>

#include <GL/gl.h>

#include <nlohmann/json.hpp>
#include <vtkActor.h>
#include <vtkCallbackCommand.h>
#include <vtkCamera.h>
#include <vtkCellArray.h>
#include <vtkDataSetMapper.h>
#include <vtkCommand.h>
#include <vtkDoubleArray.h>
#include <vtkGlyph3D.h>
#include <vtkLookupTable.h>
#include <vtkNew.h>
#include <vtkPointData.h>
#include <vtkPoints.h>
#include <vtkPolyData.h>
#include <vtkPolyDataMapper.h>
#include <vtkProperty.h>
#include <vtkGenericOpenGLRenderWindow.h>
#include <vtkGenericRenderWindowInteractor.h>
#include <vtkRenderer.h>
#include <vtkSphereSource.h>
#include <vtkVertexGlyphFilter.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <sstream>
#include <string>

namespace spike::wxui {
namespace {

wxGLAttributes CanvasAttributes() {
    wxGLAttributes multisampled;
    multisampled.PlatformDefaults().RGBA().DoubleBuffer().Depth(24).Stencil(8).SampleBuffers(1).Samplers(4).EndList();
    if (wxGLCanvas::IsDisplaySupported(multisampled)) return multisampled;
    wxGLAttributes fallback;
    fallback.PlatformDefaults().RGBA().DoubleBuffer().Depth(24).Stencil(8).EndList();
    return fallback;
}

bool Point2(const nlohmann::json& value, double& x, double& y) {
    if (!value.is_array() || value.size() < 2 || !value[0].is_number() || !value[1].is_number()) return false;
    x = value[0].get<double>();
    y = value[1].get<double>();
    return std::isfinite(x) && std::isfinite(y);
}

std::array<double, 3> TransformPoint(const nlohmann::json& frame, double x, double y, double z) {
    const auto matrix = frame.value("transform", nlohmann::json::array());
    if (!matrix.is_array() || matrix.size() != 16) return {x, y, z};
    for (const auto& value : matrix) if (!value.is_number()) return {x, y, z};
    return {
        matrix[0].get<double>() * x + matrix[1].get<double>() * y + matrix[2].get<double>() * z + matrix[3].get<double>(),
        matrix[4].get<double>() * x + matrix[5].get<double>() * y + matrix[6].get<double>() * z + matrix[7].get<double>(),
        matrix[8].get<double>() * x + matrix[9].get<double>() * y + matrix[10].get<double>() * z + matrix[11].get<double>()
    };
}

std::array<double, 4> DesignBounds(const nlohmann::json& design) {
    double min_x = std::numeric_limits<double>::infinity();
    double min_y = std::numeric_limits<double>::infinity();
    double max_x = -std::numeric_limits<double>::infinity();
    double max_y = -std::numeric_limits<double>::infinity();
    const auto retain = [&](const nlohmann::json& point) {
        double x = 0.0, y = 0.0;
        if (!Point2(point, x, y)) return;
        min_x = std::min(min_x, x); min_y = std::min(min_y, y);
        max_x = std::max(max_x, x); max_y = std::max(max_y, y);
    };
    for (const auto& track : design.value("tracks", nlohmann::json::array())) {
        if (track.is_object()) {
            retain(track.value("start_mm", nlohmann::json::array()));
            retain(track.value("end_mm", nlohmann::json::array()));
        }
    }
    for (const auto& pad : design.value("pads", nlohmann::json::array())) {
        if (pad.is_object()) retain(pad.value("position_mm", pad.value("at_mm", nlohmann::json::array())));
    }
    for (const auto& via : design.value("vias", nlohmann::json::array())) {
        if (via.is_object()) retain(via.value("position_mm", via.value("at_mm", nlohmann::json::array())));
    }
    if (!std::isfinite(min_x) || max_x <= min_x || max_y <= min_y) return {0.0, 0.0, 100.0, 80.0};
    return {min_x, min_y, max_x, max_y};
}

const nlohmann::json* FirstScalarField(const nlohmann::json& result, const std::string& preferred) {
    if (!result.contains("fields") || !result["fields"].is_object()) return nullptr;
    const auto& fields = result["fields"];
    const nlohmann::json* scalar = nullptr;
    if (fields.contains("visualization") && fields["visualization"].is_object()) {
        const auto& visual = fields["visualization"];
        if (visual.contains("scalar_fields") && visual["scalar_fields"].is_object()) scalar = &visual["scalar_fields"];
    }
    if (scalar == nullptr && fields.contains("scalar_fields") && fields["scalar_fields"].is_object()) scalar = &fields["scalar_fields"];
    if (scalar == nullptr) return nullptr;
    if (!preferred.empty() && scalar->contains(preferred) && (*scalar)[preferred].is_array()) return &(*scalar)[preferred];
    for (const auto& [name, samples] : scalar->items()) {
        (void)name;
        if (samples.is_array() && !samples.empty()) return &samples;
    }
    return nullptr;
}

}  // namespace

VtkViewport::VtkViewport(wxWindow* parent)
    : wxGLCanvas(parent, CanvasAttributes(), wxID_ANY, wxDefaultPosition, wxDefaultSize,
          wxWANTS_CHARS | wxCLIP_CHILDREN) {
    SetBackgroundStyle(wxBG_STYLE_PAINT);
    SetBackgroundColour(wxColour(18, 27, 33));
    wxGLContextAttrs context_attributes;
    context_attributes.PlatformDefaults().CoreProfile().OGLVersion(3, 2).EndList();
    context_ = std::make_unique<wxGLContext>(this, nullptr, &context_attributes);
    if (!context_->IsOK()) {
        wxGLContextAttrs compatibility_attributes;
        compatibility_attributes.PlatformDefaults().CompatibilityProfile().OGLVersion(3, 2).EndList();
        context_ = std::make_unique<wxGLContext>(this, nullptr, &compatibility_attributes);
    }
    if (!context_->IsOK()) context_ = std::make_unique<wxGLContext>(this);
    renderer_ = vtkSmartPointer<vtkRenderer>::New();
    renderer_->SetBackground(0.055, 0.09, 0.115);
    renderer_->SetBackground2(0.12, 0.18, 0.21);
    renderer_->GradientBackgroundOn();
    renderer_->UseFXAAOn();

    render_window_ = vtkSmartPointer<vtkGenericOpenGLRenderWindow>::New();
    render_window_->SetReadyForRendering(false);
    render_window_->SetOwnContext(false);
    render_window_->SetMapped(1);
    render_window_->SetFrameBlitModeToBlitToHardware();
    render_window_->AddRenderer(renderer_);
    render_window_->SetMultiSamples(4);
    render_window_->SetWindowName("SPIKE VTK Viewport");

    interactor_ = vtkSmartPointer<vtkGenericRenderWindowInteractor>::New();
    interactor_->SetRenderWindow(render_window_);

    render_window_callback_ = vtkSmartPointer<vtkCallbackCommand>::New();
    render_window_callback_->SetClientData(this);
    render_window_callback_->SetCallback(&VtkViewport::OnRenderWindowEvent);
    for (const unsigned long event_id : {
             vtkCommand::WindowMakeCurrentEvent, vtkCommand::WindowIsCurrentEvent,
             vtkCommand::WindowSupportsOpenGLEvent, vtkCommand::WindowIsDirectEvent,
             vtkCommand::WindowFrameEvent}) {
        render_window_->AddObserver(event_id, render_window_callback_);
    }

    Bind(wxEVT_SIZE, &VtkViewport::OnSize, this);
    Bind(wxEVT_SHOW, &VtkViewport::OnShow, this);
    Bind(wxEVT_PAINT, &VtkViewport::OnPaint, this);
    Bind(wxEVT_ERASE_BACKGROUND, [](wxEraseEvent&) {});
}

VtkViewport::~VtkViewport() {
    if (interactor_) interactor_->TerminateApp();
    if (render_window_) render_window_->RemoveObservers(vtkCommand::AnyEvent, render_window_callback_);
    if (!compatibility_renderer_ && render_window_ && ActivateContext()) render_window_->Finalize();
}

void VtkViewport::OnRenderWindowEvent(
    vtkObject*, unsigned long event_id, void* client_data, void* call_data) {
    auto* self = static_cast<VtkViewport*>(client_data);
    if (self == nullptr) return;
    if (event_id == vtkCommand::WindowMakeCurrentEvent) {
        const bool current = self->ActivateContext();
        if (self->render_window_) self->render_window_->SetIsCurrent(current);
    } else if (event_id == vtkCommand::WindowIsCurrentEvent) {
        const bool current = self->ActivateContext();
        if (call_data) *static_cast<bool*>(call_data) = current;
        if (self->render_window_) self->render_window_->SetIsCurrent(current);
    } else if (event_id == vtkCommand::WindowSupportsOpenGLEvent) {
        if (call_data) *static_cast<int*>(call_data) = self->context_ && self->context_->IsOK() ? 1 : 0;
    } else if (event_id == vtkCommand::WindowIsDirectEvent) {
        if (call_data) *static_cast<int*>(call_data) = 1;
    } else if (event_id == vtkCommand::WindowFrameEvent) {
        if (self->ActivateContext() && self->IsShownOnScreen()) self->SwapBuffers();
    }
}

bool VtkViewport::ActivateContext() {
    return context_ && context_->IsOK() && SetCurrent(*context_);
}

bool VtkViewport::EnsureGraphicsInitialized() {
    if (initialized_) return true;
    const auto size = GetClientSize();
    if (!IsShownOnScreen() || size.x <= 0 || size.y <= 0) return false;
    if (log_callback_) log_callback_(wxString::Format("initializing OpenGL for %dx%d canvas", size.x, size.y));
    if (!ActivateContext()) {
        if (!context_error_reported_ && log_callback_) {
            log_callback_(context_ && context_->IsOK()
                ? "OpenGL context exists but could not be made current; rendering will retry on the next paint"
                : "OpenGL 3.2 context creation failed; rendering will retry on the next paint");
            context_error_reported_ = true;
        }
        return false;
    }
    context_error_reported_ = false;
    const auto* version = reinterpret_cast<const char*>(glGetString(GL_VERSION));
    const auto* vendor = reinterpret_cast<const char*>(glGetString(GL_VENDOR));
    const auto* renderer = reinterpret_cast<const char*>(glGetString(GL_RENDERER));
    if (version == nullptr) {
        if (!context_error_reported_ && log_callback_) {
            log_callback_("OpenGL context is current but the driver returned no GL version; rendering will retry");
            context_error_reported_ = true;
        }
        return false;
    }
    if (log_callback_) {
        log_callback_(wxString::Format("wx OpenGL context is current: %s | %s | %s",
            wxString::FromUTF8(version), wxString::FromUTF8(vendor ? vendor : "unknown vendor"),
            wxString::FromUTF8(renderer ? renderer : "unknown renderer")));
    }
    int major = 0;
    int minor = 0;
    char separator = 0;
    std::istringstream version_stream(version);
    version_stream >> major >> separator >> minor;
    if (major < 3 || (major == 3 && minor < 2)) {
        compatibility_renderer_ = true;
        initialized_ = true;
        if (log_callback_) {
            log_callback_("OpenGL 3.2 is unavailable; using SPIKE's safe compatibility viewport instead of starting VTK");
        }
        return true;
    }
    render_window_->SetSize(size.x, size.y);
    render_window_->SetIsCurrent(true);
    render_window_->SetSupportsOpenGL(1);
    render_window_->SetIsDirect(1);
    render_window_->SetReadyForRendering(true);
    if (log_callback_) log_callback_("initializing VTK resources for the current OpenGL context");
    render_window_->OpenGLInitContext();
    if (log_callback_) log_callback_("initializing VTK OpenGL render state");
    render_window_->OpenGLInitState();
    if (log_callback_) log_callback_("VTK OpenGL initialization completed");
    interactor_->Initialize();
    initialized_ = true;
    if (log_callback_) log_callback_("wx-owned OpenGL context initialized for VTK");
    return true;
}

void VtkViewport::LoadDesign(const nlohmann::json& design) {
    const auto trace = [this](const wxString& message) { if (log_callback_) log_callback_(message); };
    trace("removing prior actors");
    if (board_actor_) renderer_->RemoveActor(board_actor_);
    if (via_actor_) renderer_->RemoveActor(via_actor_);
    if (assembly_actor_) {
        renderer_->RemoveActor(assembly_actor_);
        assembly_actor_ = nullptr;
    }
    fallback_segments_.clear();
    fallback_points_.clear();

    vtkNew<vtkPoints> points;
    vtkNew<vtkCellArray> lines;
    double width_sum = 0.0;
    std::size_t width_count = 0;
    if (design.contains("tracks") && design["tracks"].is_array()) {
        for (const auto& track : design["tracks"]) {
            double sx = 0.0, sy = 0.0, ex = 0.0, ey = 0.0;
            const auto& start = track.contains("start") ? track["start"] : nlohmann::json();
            const auto& end = track.contains("end") ? track["end"] : nlohmann::json();
            if (!Point2(start, sx, sy) || !Point2(end, ex, ey)) continue;
            const vtkIdType ids[] = {points->InsertNextPoint(sx, -sy, 0.0), points->InsertNextPoint(ex, -ey, 0.0)};
            lines->InsertNextCell(2, ids);
            const double width = track.value("width", track.value("width_mm", 0.2));
            fallback_segments_.push_back({sx, -sy, ex, -ey,
                std::clamp(std::isfinite(width) ? width * 6.0 : 2.0, 1.0, 5.0), false});
            if (std::isfinite(width) && width > 0.0) { width_sum += width; ++width_count; }
        }
    }
    trace(wxString::Format("prepared %lld track points", static_cast<long long>(points->GetNumberOfPoints())));
    vtkNew<vtkPolyData> track_data;
    track_data->SetPoints(points);
    track_data->SetLines(lines);
    vtkNew<vtkPolyDataMapper> track_mapper;
    track_mapper->SetInputData(track_data);
    board_actor_ = vtkSmartPointer<vtkActor>::New();
    board_actor_->SetMapper(track_mapper);
    board_actor_->GetProperty()->SetColor(0.82, 0.47, 0.13);
    board_actor_->GetProperty()->SetRoughness(0.45);
    board_actor_->GetProperty()->SetLineWidth(std::clamp(width_count ? width_sum / width_count * 6.0 : 2.0, 1.0, 5.0));
    renderer_->AddActor(board_actor_);
    trace("added track actor");

    vtkNew<vtkPoints> via_points;
    if (design.contains("vias") && design["vias"].is_array()) {
        for (const auto& via : design["vias"]) {
            double x = 0.0, y = 0.0;
            if (via.contains("at") && Point2(via["at"], x, y)) {
                via_points->InsertNextPoint(x, -y, 0.0);
                fallback_points_.push_back({x, -y, 0.0, false});
            }
        }
    }
    trace(wxString::Format("prepared %lld via points", static_cast<long long>(via_points->GetNumberOfPoints())));
    if (via_points->GetNumberOfPoints() > 0) {
        vtkNew<vtkPolyData> via_data;
        via_data->SetPoints(via_points);
        vtkNew<vtkSphereSource> sphere;
        sphere->SetRadius(0.25);
        sphere->SetThetaResolution(10);
        sphere->SetPhiResolution(8);
        vtkNew<vtkGlyph3D> glyphs;
        glyphs->SetSourceConnection(sphere->GetOutputPort());
        glyphs->SetInputData(via_data);
        vtkNew<vtkPolyDataMapper> via_mapper;
        via_mapper->SetInputConnection(glyphs->GetOutputPort());
        via_actor_ = vtkSmartPointer<vtkActor>::New();
        via_actor_->SetMapper(via_mapper);
        via_actor_->GetProperty()->SetColor(0.75, 0.78, 0.8);
        renderer_->AddActor(via_actor_);
    } else {
        via_actor_ = nullptr;
    }
    trace("fitting camera and rendering");
    Fit();
    trace("render completed");
}

void VtkViewport::LoadAssembly(const nlohmann::json& assembly, const nlohmann::json& designs) {
    if (board_actor_) { renderer_->RemoveActor(board_actor_); board_actor_ = nullptr; }
    if (via_actor_) { renderer_->RemoveActor(via_actor_); via_actor_ = nullptr; }
    if (assembly_actor_) renderer_->RemoveActor(assembly_actor_);
    ClearResult();
    fallback_segments_.clear();
    fallback_points_.clear();
    vtkNew<vtkPoints> points;
    vtkNew<vtkCellArray> lines;
    std::size_t rendered = 0;
    for (const auto& board : assembly.value("boards", nlohmann::json::array())) {
        if (!board.is_object() || rendered >= 20) break;
        const auto id = board.value("design_id", "");
        const auto design = designs.is_object() && designs.contains(id) ? designs[id] : nlohmann::json::object();
        const auto bounds = DesignBounds(design);
        const std::array<std::array<double, 3>, 5> corners = {{
            {bounds[0], bounds[1], 0.0}, {bounds[2], bounds[1], 0.0}, {bounds[2], bounds[3], 0.0},
            {bounds[0], bounds[3], 0.0}, {bounds[0], bounds[1], 0.0}
        }};
        vtkIdType ids[5];
        for (std::size_t index = 0; index < corners.size(); ++index) {
            const auto transformed = TransformPoint(board.value("frame", nlohmann::json::object()),
                corners[index][0], corners[index][1], corners[index][2]);
            ids[index] = points->InsertNextPoint(transformed[0], -transformed[1], transformed[2]);
            if (index > 0) {
                const auto previous = TransformPoint(board.value("frame", nlohmann::json::object()),
                    corners[index - 1][0], corners[index - 1][1], corners[index - 1][2]);
                fallback_segments_.push_back({previous[0], -previous[1], transformed[0], -transformed[1], 3.0, true});
            }
        }
        lines->InsertNextCell(5, ids);
        ++rendered;
    }
    vtkNew<vtkPolyData> data;
    data->SetPoints(points);
    data->SetLines(lines);
    vtkNew<vtkPolyDataMapper> mapper;
    mapper->SetInputData(data);
    assembly_actor_ = vtkSmartPointer<vtkActor>::New();
    assembly_actor_->SetMapper(mapper);
    assembly_actor_->GetProperty()->SetColor(0.25, 0.78, 0.72);
    assembly_actor_->GetProperty()->SetLineWidth(3.0);
    renderer_->AddActor(assembly_actor_);
    if (log_callback_) log_callback_(wxString::Format("rendered %zu assembly board envelopes", rendered));
    Fit();
}

void VtkViewport::LoadResult(const nlohmann::json& result, const std::string& preferred_metric) {
    ClearResult();
    const auto* samples = FirstScalarField(result, preferred_metric);
    if (samples == nullptr) return;
    vtkNew<vtkPoints> points;
    vtkNew<vtkDoubleArray> scalars;
    scalars->SetName("result");
    double minimum = std::numeric_limits<double>::infinity();
    double maximum = -std::numeric_limits<double>::infinity();
    for (const auto& sample : *samples) {
        if (!sample.is_object()) continue;
        const double x = sample.value("x_mm", std::numeric_limits<double>::quiet_NaN());
        const double y = sample.value("y_mm", std::numeric_limits<double>::quiet_NaN());
        const double z = sample.value("z_mm", 0.15);
        const double value = sample.value("value", std::numeric_limits<double>::quiet_NaN());
        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(value)) continue;
        points->InsertNextPoint(x, -y, z);
        scalars->InsertNextValue(value);
        fallback_points_.push_back({x, -y, value, true});
        minimum = std::min(minimum, value);
        maximum = std::max(maximum, value);
    }
    if (points->GetNumberOfPoints() == 0) return;
    vtkNew<vtkPolyData> data;
    data->SetPoints(points);
    data->GetPointData()->SetScalars(scalars);
    vtkNew<vtkVertexGlyphFilter> vertices;
    vertices->SetInputData(data);
    vertices->Update();
    vtkNew<vtkLookupTable> colors;
    colors->SetHueRange(0.67, 0.0);
    colors->SetNumberOfTableValues(256);
    colors->Build();
    vtkNew<vtkPolyDataMapper> mapper;
    mapper->SetInputConnection(vertices->GetOutputPort());
    mapper->SetLookupTable(colors);
    mapper->SetScalarRange(minimum, maximum > minimum ? maximum : minimum + 1.0);
    result_actor_ = vtkSmartPointer<vtkActor>::New();
    result_actor_->SetMapper(mapper);
    result_actor_->GetProperty()->SetPointSize(8.0);
    renderer_->AddActor(result_actor_);
    Render();
}

void VtkViewport::ClearResult() {
    fallback_points_.erase(std::remove_if(fallback_points_.begin(), fallback_points_.end(),
        [](const FallbackPoint& point) { return point.result; }), fallback_points_.end());
    if (result_actor_) {
        renderer_->RemoveActor(result_actor_);
        result_actor_ = nullptr;
        Render();
    }
}

void VtkViewport::Fit() {
    renderer_->ResetCamera();
    renderer_->GetActiveCamera()->ParallelProjectionOn();
    renderer_->ResetCameraClippingRange();
    Render();
}

void VtkViewport::SetTopView() {
    auto* camera = renderer_->GetActiveCamera();
    camera->SetPosition(0.0, 0.0, 1.0);
    camera->SetFocalPoint(0.0, 0.0, 0.0);
    camera->SetViewUp(0.0, 1.0, 0.0);
    camera->ParallelProjectionOn();
    renderer_->ResetCamera();
    renderer_->ResetCameraClippingRange();
    Render();
}

void VtkViewport::SetPerspectiveView() {
    auto* camera = renderer_->GetActiveCamera();
    renderer_->ResetCamera();
    camera->ParallelProjectionOff();
    camera->Azimuth(35.0);
    camera->Elevation(45.0);
    camera->OrthogonalizeViewUp();
    renderer_->ResetCameraClippingRange();
    Render();
}

void VtkViewport::OnSize(wxSizeEvent& event) {
    const auto size = GetClientSize();
    if (render_window_ && size.x > 0 && size.y > 0) {
        render_window_->SetSize(size.x, size.y);
        Refresh(false);
    }
    event.Skip();
}

void VtkViewport::OnShow(wxShowEvent& event) {
    if (event.IsShown()) CallAfter([this] { Refresh(false); });
    event.Skip();
}

void VtkViewport::OnPaint(wxPaintEvent&) {
    wxPaintDC paint(this);
    (void)paint;
    if (!EnsureGraphicsInitialized()) return;
    Render();
}

void VtkViewport::Render() {
    auto* top = wxDynamicCast(wxGetTopLevelParent(this), wxTopLevelWindow);
    if (!render_window_ || !IsShownOnScreen() || (top && top->IsIconized())) return;
    if (!EnsureGraphicsInitialized() || !ActivateContext()) return;
    const auto size = GetClientSize();
    if (size.x <= 0 || size.y <= 0) return;
    if (compatibility_renderer_) {
        RenderCompatibility();
        return;
    }
    render_window_->SetSize(size.x, size.y);
    render_window_->SetIsCurrent(true);
    render_window_->SetReadyForRendering(true);
    render_window_->Render();
}

void VtkViewport::RenderCompatibility() {
    const auto size = GetClientSize();
    if (size.x <= 0 || size.y <= 0) return;

    double min_x = std::numeric_limits<double>::infinity();
    double min_y = std::numeric_limits<double>::infinity();
    double max_x = -std::numeric_limits<double>::infinity();
    double max_y = -std::numeric_limits<double>::infinity();
    const auto include = [&](double x, double y) {
        min_x = std::min(min_x, x);
        min_y = std::min(min_y, y);
        max_x = std::max(max_x, x);
        max_y = std::max(max_y, y);
    };
    for (const auto& segment : fallback_segments_) {
        include(segment.x1, segment.y1);
        include(segment.x2, segment.y2);
    }
    for (const auto& point : fallback_points_) include(point.x, point.y);
    if (!std::isfinite(min_x) || max_x <= min_x || max_y <= min_y) {
        min_x = 0.0; min_y = 0.0; max_x = 100.0; max_y = 80.0;
    }
    const double content_width = std::max(1.0, max_x - min_x);
    const double content_height = std::max(1.0, max_y - min_y);
    const double center_x = (min_x + max_x) * 0.5;
    const double center_y = (min_y + max_y) * 0.5;
    double view_width = content_width * 1.12;
    double view_height = content_height * 1.12;
    const double window_aspect = static_cast<double>(size.x) / static_cast<double>(size.y);
    if (view_width / view_height < window_aspect) view_width = view_height * window_aspect;
    else view_height = view_width / window_aspect;

    glViewport(0, 0, size.x, size.y);
    glDisable(GL_DEPTH_TEST);
    glClearColor(0.055f, 0.09f, 0.115f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glOrtho(center_x - view_width * 0.5, center_x + view_width * 0.5,
        center_y - view_height * 0.5, center_y + view_height * 0.5, -1.0, 1.0);
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glEnable(GL_LINE_SMOOTH);
    glHint(GL_LINE_SMOOTH_HINT, GL_NICEST);

    for (const auto& segment : fallback_segments_) {
        glLineWidth(static_cast<GLfloat>(segment.width));
        if (segment.assembly) glColor4f(0.25f, 0.78f, 0.72f, 1.0f);
        else glColor4f(0.86f, 0.51f, 0.16f, 1.0f);
        glBegin(GL_LINES);
        glVertex2d(segment.x1, segment.y1);
        glVertex2d(segment.x2, segment.y2);
        glEnd();
    }

    double result_min = std::numeric_limits<double>::infinity();
    double result_max = -std::numeric_limits<double>::infinity();
    for (const auto& point : fallback_points_) if (point.result) {
        result_min = std::min(result_min, point.value);
        result_max = std::max(result_max, point.value);
    }
    for (const bool results : {false, true}) {
        glPointSize(results ? 8.0f : 6.0f);
        glBegin(GL_POINTS);
        for (const auto& point : fallback_points_) {
            if (point.result != results) continue;
            if (results) {
                const double span = result_max > result_min ? result_max - result_min : 1.0;
                const float value = static_cast<float>(std::clamp((point.value - result_min) / span, 0.0, 1.0));
                glColor4f(value, 0.2f, 1.0f - value, 1.0f);
            } else {
                glColor4f(0.78f, 0.82f, 0.85f, 1.0f);
            }
            glVertex2d(point.x, point.y);
        }
        glEnd();
    }
    glDisable(GL_LINE_SMOOTH);
    glFlush();
    SwapBuffers();
}

}  // namespace spike::wxui
