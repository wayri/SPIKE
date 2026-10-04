import emerge as em
import numpy as np
from functools import reduce

"""
In this demo file we will model radiator panels which are used in Space to radiate
away heat using black body radiation.

Please keep in mind that this model is HIGHLY UNREALISTIC. In reality there are
fluid channels used to transport heat through these panels. This is just a very
simple toy model to illustrate the application of the boundary condition.

We will model a sequence of 4 panels connected by a 1cm x 1cm aluminium bar 
with a fluid channel inside it that has a high thermal conductivity.

The radiator panels have a black-body radiation boundary condition to 5K ambient.

1000W of heat is introduced at the feed point of the fluid channel.
"""
mm = 0.001
cm = 0.01
deg = np.pi / 180

Wbar = 1 * cm

Wpanel = 80 * cm
Lpanel = 50 * cm
thpanel = 0.5 * cm

Npanels = 4
gap = 2 * cm

panel_angle = 5 * deg

# --- Materials

mat_fluid = em.Material(cond_thermal=1000.0, color="#84a2e8")

# ---- Derived quantities
Ltrue = Lpanel * np.cos(panel_angle)

dx = Ltrue + gap

# ---- Simulation object

model = em.Simulation("Radiator Panel")
model.set_physics(False, True)

# Model the radiator panels with rotation.
panels = []
for i in range(Npanels):
    panel = em.geo.Box(Lpanel, Wpanel, thpanel, position=(i * dx, 0, 0)).set_material(
        em.lib.MET_ALUMINUM
    )
    em.geo.rotate(
        panel,
        (i * dx + Ltrue / 2, 0, 0),
        (0, 1, 0),
        ((-1) ** i) * panel_angle,
        degree=False,
    )
    panel.max_meshsize = Wpanel / 10
    panels.append(panel)

# Model the connecting structure
bar_1 = em.geo.Box(Npanels * dx, Wbar, Wbar, (0, -Wbar, -Wbar / 2)).set_material(
    em.lib.MET_ALUMINUM
)
fluid = (
    em.geo.Cylinder(
        Wbar / 4, Npanels * dx, em.XAX.construct_cs((0, -Wbar / 2, 0)), Nsections=12
    )
    .set_material(mat_fluid)
    .foreground()
)

# We set an initial temperature as a good guess to help convergence of
# the non-linear solver.
model.hc.set_initial_temperature(50)

model.commit_geometry()

# Generate mesh and view.
model.generate_mesh()
model.view()
model.view(plot_mesh=True)

# We have to make a selection of all the top and bottom faces of the structure
# We will put them in  a list and then use the reduce function to combine them
# into a single selection.
selections = []
for panel in panels:
    selections.append(panel.top)
    selections.append(panel.bottom)

bb_selection = reduce(lambda a, b: a + b, selections)

# We assign with an emissivity of 0.85 to 5 Kelvin.
model.hc.bc.BlackBodyRadiation(bb_selection, 0.85, 5)

# We inject 1000W of heat in the fluit front entrance.
model.hc.bc.HeatFluxBoundary(fluid.front, 1000.0)

model.view(bc=True)

# We can just run the model as is.
solution = model.hc.run_steady_state_nl()


# And we view the temperatures on the boundary.
disp = model.display
disp.populate(opacity=0.1)
disp.cbar("Temperature (K)").add_field(
    solution.field[0].boundary(model.all_boundaries()).scalar("T")
)
disp.show()
