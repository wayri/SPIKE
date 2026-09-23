# The current source package publishes the GUI contracts and implementation
# plan without pretending the desktop executable exists.  This target keeps the
# source visible in IDEs until the M0 wxWidgets/VTK shell lands.
add_custom_target(spikes_studio_contracts SOURCES
    "${CMAKE_CURRENT_LIST_DIR}/../docs/GUI_PRODUCT_PLAN.md"
    "${CMAKE_CURRENT_LIST_DIR}/../docs/GUI_ARCHITECTURE.md"
    "${CMAKE_CURRENT_LIST_DIR}/../schemas/studio-part-v1.schema.json"
    "${CMAKE_CURRENT_LIST_DIR}/../schemas/studio-project-v1.schema.json"
    "${CMAKE_CURRENT_LIST_DIR}/../python/spikes_studio/model_import.py"
)
message(STATUS "SPIKES Studio contracts enabled; the native wxWidgets/VTK executable starts in milestone M0")
