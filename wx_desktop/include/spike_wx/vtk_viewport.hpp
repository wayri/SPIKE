#pragma once

#include <wx/glcanvas.h>

#include <nlohmann/json_fwd.hpp>
#include <functional>
#include <memory>
#include <vector>
#include <vtkSmartPointer.h>

class vtkActor;
class vtkCallbackCommand;
class vtkAxesActor;
class vtkOrientationMarkerWidget;
class vtkRenderer;
class vtkGenericOpenGLRenderWindow;
class vtkGenericRenderWindowInteractor;
class vtkObject;

namespace spike::wxui {

class VtkViewport final : public wxGLCanvas {
public:
    explicit VtkViewport(wxWindow* parent);
    ~VtkViewport() override;

    void LoadDesign(const nlohmann::json& design);
    void LoadAssembly(const nlohmann::json& assembly, const nlohmann::json& designs);
    void SetLogCallback(std::function<void(const wxString&)> callback) { log_callback_ = std::move(callback); }
    void LoadResult(const nlohmann::json& result, const std::string& preferred_metric = {});
    void ClearResult();
    void Fit();
    void SetTopView();
    void SetPerspectiveView();

private:
    struct FallbackSegment {
        double x1{};
        double y1{};
        double x2{};
        double y2{};
        double width{1.0};
        bool assembly{};
    };

    struct FallbackPoint {
        double x{};
        double y{};
        double value{};
        bool result{};
    };

    static void OnRenderWindowEvent(
        vtkObject* caller, unsigned long event_id, void* client_data, void* call_data);
    bool EnsureGraphicsInitialized();
    bool ActivateContext();
    void OnSize(wxSizeEvent& event);
    void OnShow(wxShowEvent& event);
    void OnPaint(wxPaintEvent& event);
    void Render();
    void RenderCompatibility();

    vtkSmartPointer<vtkRenderer> renderer_;
    std::unique_ptr<wxGLContext> context_;
    vtkSmartPointer<vtkGenericOpenGLRenderWindow> render_window_;
    vtkSmartPointer<vtkGenericRenderWindowInteractor> interactor_;
    vtkSmartPointer<vtkCallbackCommand> render_window_callback_;
    vtkSmartPointer<vtkActor> board_actor_;
    vtkSmartPointer<vtkActor> via_actor_;
    vtkSmartPointer<vtkActor> assembly_actor_;
    vtkSmartPointer<vtkActor> result_actor_;
    bool initialized_{false};
    bool compatibility_renderer_{false};
    bool context_error_reported_{false};
    std::vector<FallbackSegment> fallback_segments_;
    std::vector<FallbackPoint> fallback_points_;
    std::function<void(const wxString&)> log_callback_;
};

}  // namespace spike::wxui
