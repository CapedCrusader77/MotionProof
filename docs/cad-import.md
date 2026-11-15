# CAD import

| Format | What is read | Units |
|---|---|---|
| STEP | Solids, volume, area, bounding box, centre of mass, validity; part names when the assembly structure matches the solid count | Millimetres (OpenCascade converts using the units in the file) |
| STL, OBJ | One mesh: watertightness, winding, volume when closed | **Unknown** unless you state one; nothing is scaled or guessed |
| URDF, MJCF | Bodies, joints, masses via MuJoCo; geometry meshed for display | SI |

The original file is copied to `original/` and never changed. Mass is undefined for STEP and
mesh imports because they carry no reliable density. Import failures say what is wrong and what
to do (for example "contains no solid bodies: export solids from the CAD system").

Fusion 360: export MJCF with an existing add-in (ACDC4Robot or Fusion2Mujoco) and import that
file together with its meshes. This path has not been tested with a real Fusion assembly.

A STEP or mesh import is geometry only: features, tolerances and fit analysis work, simulation
needs a URDF or MJCF model.
