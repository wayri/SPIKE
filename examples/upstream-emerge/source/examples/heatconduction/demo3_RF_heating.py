import emerge as em

"""
In this example we will look at how we can couple our RF simulations to the heat conduction physics.

The example concerns a simple WR90 waveguide with in it a block of dielectric material. In this case 
FR4.

The waveguide port will be excited with a 100W signal. Then the losses will be imported into the
heat conduction physics module.

For the heat conduction physics, the bottom of the 1mm thick WR90 guide will be connected to thermal ambient
using a 1000 [W/m²K] connection.
"""

# --- Definitions and parameters
mm = 0.001
wga = 22.86 * mm
wgb = 10.16 * mm
L = 50 * mm

lblock = 10 * mm
hblock = 4 * mm

thmet = 1 * mm

T_amb = 293.15

dielmat = em.lib.DIEL_FR4

# --- Simulation setup
sim = em.Simulation("ThermalTest")

# We activate both microwave and heat transfer physics
sim.set_physics(True, True)

# First we create the outer box which will represent our wavegudie wall, including the thickness.
box_wall_orig = em.geo.Box(
    wga + 2 * thmet, L, wgb + 2 * thmet, (-wga / 2 - thmet, -L / 2, -thmet)
).set_material(em.lib.COPPER)

# Next we create an inside air box with the waveguide WR90 dimensions
box_air = em.geo.Box(wga, L, wgb, (-wga / 2, -L / 2, 0)).prio_up()

# The wall geometry is the original box minus air. We want to keep the air itself so we turn
# off remove-tool. Otherwise the air domain will not be meshed.
box_wall = em.geo.subtract(box_wall_orig, box_air, remove_tool=False)

# Finally we add our dielectric block. We add .foreground() to make sure its material assignment
# takes priority over air.
diel = (
    em.geo.Box(wga, lblock, hblock, position=(-wga / 2, (-lblock / 2), 0))
    .set_material(dielmat)
    .foreground()
)

# We finish our simulation with commit geometry
sim.commit_geometry()

# --- Mesh settings

# first we define our simulation frequency. This defines a maximum element size
sim.mw.set_frequency(10e9)
sim.mw.set_resolution(0.2)  # mesh resolution as 0.2 x wavelength

# Then we generate our mesh
sim.generate_mesh()

# and view the result!
sim.view()
sim.view(plot_mesh=True)


############################################################
#                       RF SIMULATION                      #
############################################################


# We can first define the microwave physics boundary conditions. In this case two rectangular waveguides.
sim.mw.bc.RectangularWaveguide(box_air.front, 1)
sim.mw.bc.RectangularWaveguide(box_air.back, 2)

# This is already enough to simulate our model
mw_solutions = sim.mw.run_sweep()

# We can make a view of our volumetric heat dissipation
d = sim.display

# We populate our geometry with a 0.2 opacity to see the fields
d.populate(opacity=0.2)

# We createa  field object with a volumetric grid of 10_000 points
mwfield = mw_solutions.field[0].grid(N=10_000)

# we also create a cutplane along the length of th waveguide to animate our E-field
mwcut = mw_solutions.field[0].cutplane(ds=1 * mm, x=-2 * mm)

# We fill our plot with the volumetric heat dissipation and
d.cbar("Qv (W/m³)").add_field(mwfield.scalar("Qv"), cmap="plasma")
d.animate().add_field(mwcut.scalar("Ez", "complex"), symmetrize=True)
d.show()


############################################################
#                      HEAT CONDUCTION                     #
############################################################

# Our heat conduction part is quite simple. First we set a 1000 W/m2K for our bottom copper boundary
sim.hc.bc.Convection(box_wall.face("bottom", tool=box_wall_orig), 1000.0, T_amb)

# To take the losses from our field solution and inject them into our simulation we use the
# CoupledEMHeating boundary condition.
#  - The first argument is the domain(s) in which we want to inject the losses. In this case we can
# just select the dielectric block and ignore the rest.
#  - The second argument is the field solution object. Because we ran just one simulation its simply
#    mw_solutions.field[0]
#  - The third argument is a vector of power excitations for each port. You can also change this manually
#    by calling set_excitation() on the field object but we will just use this argument. Because we have
#    two ports we supply a list of two arguments
sim.hc.bc.CoupledEMHeating(diel, mw_solutions.field[0], excitation_W=[100, 0])

# Finally we call our stead-state solver
mw_solutions = sim.hc.run_steady_state()


# Next we build a new plot
d = sim.display

# This helps making cutplanes a bit clearer.
d.set.theme.render_shadows = False

d.populate(opacity=0.001)
d.cbar("T (C)").add_field(
    mw_solutions.field[0].cutplane(ds=0.25 * mm, x=0).scalar("TdegC"),
)
d.cbar("Q [W/m2]").add_field(
    mw_solutions.field[0].cutplane(ds=0.5 * mm, x=0.5 * mm).vector("q"), color="yellow"
)
d.show()
