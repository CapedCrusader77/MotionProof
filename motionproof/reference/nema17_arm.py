"""Synthetic reference design: NEMA 17 + two-stage planetary gearbox + two-link arm.

THIS IS NOT USER HARDWARE. It is a parameterised CadQuery model created by MotionProof so the
tolerance-to-dynamics workflow can be demonstrated and tested end to end. Tooth counts were
chosen to realise the 33:1 *target* ratio exactly (5.5 x 6); gears are drawn as pitch cylinders
for visualisation only. Every tolerance, motor and gearbox value attached to it is an
illustrative assumption and is labelled as such in the model file.

Coordinates: millimetres, gearbox axis along +Y, arm along +X at the reference pose, Z up.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np
import yaml

from motionproof.core.transforms import combine_inertias

GENERATOR = "nema17_planetary_arm"
STEEL, ALUMINIUM = 7850.0, 2700.0  # kg/m^3, assumed materials of the synthetic design

DEFAULTS: dict[str, float] = {
    "output_shaft_diameter": 8.0,
    "bearing_bore_diameter": 8.0,
    "bearing_outer_diameter": 22.0,
    "housing_seat_diameter": 22.0,
    "input_shaft_diameter": 5.0,
    "mount_hole_diameter": 3.2,
    "mount_hole_dx": 0.0,
    "mount_hole_dy": 0.0,
    "s1_pin_radial_0": 0.0, "s1_pin_radial_1": 0.0, "s1_pin_radial_2": 0.0,
    "s2_pin_radial_0": 0.0, "s2_pin_radial_1": 0.0, "s2_pin_radial_2": 0.0,
    "upper_arm_length": 200.0,
    "forearm_length": 150.0,
}

STAGES: tuple[dict[str, Any], ...] = (
    {"id": "stage1", "sun": 12, "planet": 21, "ring": 54, "module": 0.5, "z": (-14.0, -6.0)},
    {"id": "stage2", "sun": 12, "planet": 24, "ring": 60, "module": 0.5, "z": (0.0, 8.0)},
)
BEARING_SPAN = 15.0  # mm between the two output bearing rows
# tolerance ids whose actual value regenerates geometry (Level A)
GEOMETRY_PARAMETERS = [
    "output_shaft_diameter", "bearing_bore_diameter", "bearing_outer_diameter",
    "housing_seat_diameter", "mount_hole_dx", "mount_hole_dy",
    *[f"s{s}_pin_radial_{k}" for s in (1, 2) for k in range(3)],
]


@dataclass
class Part:
    name: str
    body: str  # base | upper_arm | forearm
    solid: cq.Shape
    density: float
    group: str
    note: str = ""


def _cyl(d: float, z0: float, z1: float, x: float = 0.0, y: float = 0.0) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(d / 2).extrude(z1 - z0)


def _to_world(wp: cq.Workplane) -> cq.Shape:
    """Gearbox-local (axis Z) to world (axis Y)."""
    from motionproof.cad.features import as_shape

    return as_shape(wp.rotate((0, 0, 0), (1, 0, 0), -90))


def build_parts(params: dict[str, float] | None = None,
                only: set[str] | None = None) -> list[Part]:
    """Regenerate the solids. ``only`` restricts the build to the named parts."""
    p = {**DEFAULTS, **(params or {})}
    unknown = set(p) - set(DEFAULTS)
    if unknown:
        raise KeyError(f"unknown reference-design parameters: {sorted(unknown)}")
    parts: list[Part] = []

    def want(name: str) -> bool:
        return only is None or name in only

    def add(name: str, body: str, wp: cq.Workplane, density: float, group: str,
            note: str = "") -> None:
        solid = _to_world(wp)
        if not solid.isValid() or solid.Volume() <= 0:
            raise ValueError(f"regenerated part {name!r} is not a valid solid")
        parts.append(Part(name, body, solid, density, group, note))

    # --- fixed structure ---------------------------------------------------------
    if want("motor_body"):
        motor = cq.Workplane("XY").workplane(offset=-60).rect(42.3, 42.3).extrude(40)
        add("motor_body", "base", motor, 4500.0, "motor", "effective density of a wound stator")
    if want("input_shaft"):
        add("input_shaft", "base", _cyl(p["input_shaft_diameter"], -20, -5), STEEL, "motor")
    if want("housing"):
        housing = cq.Workplane("XY").workplane(offset=-20).circle(21).extrude(56)
        housing = housing.union(
            cq.Workplane("XY").workplane(offset=-20).rect(42.3, 42.3).extrude(4))
        housing = housing.cut(_cyl(34, -18, 12))  # gear cavity
        housing = housing.cut(_cyl(10, 12, 36))  # shaft passage
        seat = p["housing_seat_diameter"]
        housing = housing.cut(_cyl(seat, 13, 20)).cut(_cyl(seat, 28, 35))
        for sx in (-1, 1):
            for sy in (-1, 1):
                housing = housing.cut(_cyl(p["mount_hole_diameter"], -20, -16,
                                           15.5 * sx + p["mount_hole_dx"],
                                           15.5 * sy + p["mount_hole_dy"]))
        add("housing", "base", housing, ALUMINIUM, "housing")
    for i, z0 in enumerate((13.0, 28.0)):
        if want(f"output_bearing_{i}"):
            ring = (cq.Workplane("XY").workplane(offset=z0)
                    .circle(p["bearing_outer_diameter"] / 2)
                    .circle(p["bearing_bore_diameter"] / 2).extrude(7))
            add(f"output_bearing_{i}", "base", ring, STEEL, "bearing",
                "drawn as a solid ring; no rolling elements")

    # --- gear train (pitch-cylinder representation) ---------------------------------
    for s_idx, st in enumerate(STAGES, start=1):
        z0, z1 = st["z"]
        m = st["module"]
        a = m * (st["sun"] + st["planet"]) / 2
        if want(f"{st['id']}_ring"):
            ring = (cq.Workplane("XY").workplane(offset=z0).circle(17)
                    .circle(m * st["ring"] / 2).extrude(z1 - z0))
            add(f"{st['id']}_ring", "base", ring, STEEL, "gear", "pitch-cylinder representation")
        if want(f"{st['id']}_sun"):
            add(f"{st['id']}_sun", "base", _cyl(m * st["sun"], z0, z1), STEEL, "gear",
                "pitch-cylinder representation")
        carrier = _cyl(2 * a + 8, z1 + 1, z1 + 3)
        for k in range(3):
            ang = 2 * np.pi * k / 3
            r = a + p[f"s{s_idx}_pin_radial_{k}"]
            x, y = r * np.cos(ang), r * np.sin(ang)
            if want(f"{st['id']}_planet_{k}"):
                planet = (cq.Workplane("XY").workplane(offset=z0).center(x, y)
                          .circle(m * st["planet"] / 2).circle(1.5).extrude(z1 - z0))
                add(f"{st['id']}_planet_{k}", "base", planet, STEEL, "gear",
                    "pitch-cylinder representation")
            carrier = carrier.union(_cyl(3.0, z0, z1 + 1, x, y))
        if want(f"{st['id']}_carrier"):
            add(f"{st['id']}_carrier", "base", carrier, STEEL, "gear")

    # --- moving links -----------------------------------------------------------------
    la, lf = p["upper_arm_length"], p["forearm_length"]
    if want("output_shaft"):
        add("output_shaft", "upper_arm", _cyl(p["output_shaft_diameter"], 11, 52), STEEL, "shaft")
    if want("upper_arm_link"):
        hub = _cyl(20, 38, 50).cut(_cyl(p["output_shaft_diameter"], 38, 50))
        bar = (cq.Workplane("XY").workplane(offset=38).center(la / 2, 0).rect(la + 20, 20)
               .extrude(12).cut(_cyl(20, 38, 50)))
        add("upper_arm_link", "upper_arm", hub.union(bar), ALUMINIUM, "link")
    if want("forearm_link"):
        fore = (cq.Workplane("XY").workplane(offset=50).center(la + lf / 2, 0)
                .rect(lf + 20, 16).extrude(10))
        add("forearm_link", "forearm", fore, ALUMINIUM, "link")
    return parts


def part_properties(part: Part) -> dict[str, Any]:
    s = part.solid
    vol = float(s.Volume())  # mm^3
    com = cq.Shape.centerOfMass(s)
    inertia = np.array(cq.Shape.matrixOfInertia(s), dtype=float)  # unit density, mm^5, at COM
    bb = s.BoundingBox()
    return {
        "volume_mm3": vol,
        "area_mm2": float(s.Area()),
        "mass_kg": part.density * vol * 1e-9,
        "density_kg_m3": part.density,
        "com_m": [com.x * 1e-3, com.y * 1e-3, com.z * 1e-3],
        "inertia_com_kgm2": (inertia * part.density * 1e-15).tolist(),
        "bbox_mm": [[bb.xmin, bb.ymin, bb.zmin], [bb.xmax, bb.ymax, bb.zmax]],
    }


def body_inertials(parts: list[Part]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for body in ("upper_arm", "forearm"):
        triples = []
        for part in parts:
            if part.body == body:
                pr = part_properties(part)
                triples.append((pr["mass_kg"], np.array(pr["com_m"]),
                                np.array(pr["inertia_com_kgm2"])))
        mass, com, inertia = combine_inertias(triples)
        out[body] = {"mass": mass, "com": com.tolist(), "inertia": inertia.tolist()}
    return out


def joint_layout(params: dict[str, float] | None = None) -> dict[str, Any]:
    p = {**DEFAULTS, **(params or {})}
    la, lf = p["upper_arm_length"] * 1e-3, p["forearm_length"] * 1e-3
    return {
        "shoulder": {"pos": [0.0, 0.044, 0.0], "axis": [0.0, -1.0, 0.0]},
        "elbow": {"pos": [la, 0.050, 0.0], "axis": [0.0, -1.0, 0.0]},
        "end_effector": [la + lf, 0.055, 0.0],
    }


def build_mjcf(params: dict[str, float] | None = None, parts: list[Part] | None = None) -> str:
    """Dynamics model: explicit inertials from the CAD solids, no contact geometry.

    Joint axes point along -Y so that positive angles raise the arm against gravity.
    """
    parts = parts or build_parts(params)
    inert = body_inertials(parts)
    lay = joint_layout(params)

    def vec(v: list[float]) -> str:
        return " ".join(f"{x:.9g}" for x in v)

    def inertial(body: str) -> str:
        b = inert[body]
        i = np.array(b["inertia"])
        full = [i[0, 0], i[1, 1], i[2, 2], i[0, 1], i[0, 2], i[1, 2]]
        return (f'<inertial pos="{vec(b["com"])}" mass="{b["mass"]:.9g}" '
                f'fullinertia="{vec(full)}"/>')

    sh, el = lay["shoulder"], lay["elbow"]
    return f"""<mujoco model="{GENERATOR}">
  <compiler angle="radian" autolimits="true"/>
  <option gravity="0 0 -9.81" timestep="0.0005" integrator="implicitfast"/>
  <worldbody>
    <body name="base"/>
    <body name="upper_arm">
      <joint name="shoulder" type="hinge" pos="{vec(sh['pos'])}" axis="{vec(sh['axis'])}" range="-3.0 3.0"/>
      {inertial('upper_arm')}
      <body name="forearm">
        <joint name="elbow" type="hinge" pos="{vec(el['pos'])}" axis="{vec(el['axis'])}" range="-2.4 2.4"/>
        {inertial('forearm')}
      </body>
    </body>
  </worldbody>
</mujoco>
"""


def write_geometry(directory: str | Path, params: dict[str, float] | None = None,
                   tolerance: float = 0.02) -> dict[str, Any]:
    """Export one STL per component, a STEP of the whole assembly, the MJCF and an inventory."""
    out = Path(directory)
    (out / "meshes").mkdir(parents=True, exist_ok=True)
    parts = build_parts(params)
    assembly = cq.Assembly(name=GENERATOR)
    components = []
    for part in parts:
        mesh_file = f"meshes/{part.name}.stl"
        part.solid.exportStl(str(out / mesh_file), tolerance, 0.2)
        assembly.add(part.solid, name=part.name)
        components.append({"id": part.name, "name": part.name, "body": part.body,
                           "group": part.group, "mesh": mesh_file, "mesh_units": "mm",
                           "note": part.note, "source": "generated (CadQuery)",
                           **part_properties(part)})
    step = out / "assembly.step"
    assembly.export(str(step))
    # OpenCASCADE stamps the write time into the header; a fixed stamp keeps regenerated files
    # byte-identical when the geometry has not changed.
    text = step.read_text(encoding="utf-8")
    step.write_text(re.sub(r"(FILE_NAME\('[^']*',')[^']*(')", r"\g<1>2000-01-01T00:00:00\g<2>",
                           text, count=1), encoding="utf-8")
    (out / "model.xml").write_text(build_mjcf(params, parts), encoding="utf-8")
    inventory = {
        "generator": GENERATOR,
        "synthetic": True,
        "parameters": {**DEFAULTS, **(params or {})},
        "units": {"geometry": "mm", "dynamics": "SI"},
        "components": components,
        "bodies": body_inertials(parts),
        "joints": joint_layout(params),
    }
    (out / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return inventory


def measure_variant_geometry(values: dict[str, float]) -> dict[str, Any]:
    """Level A: regenerate the toleranced parts for actual values and measure them (OCC).

    Only parameters with a geometric definition in this design are regenerated; everything
    else in ``values`` is ignored here and handled by the reduced-order relations.
    """
    from motionproof.cad.features import cylindrical_features, interference_volume, min_distance

    params = {k: values[k] for k in GEOMETRY_PARAMETERS if k in values}
    names = {"output_shaft", "output_bearing_0", "housing", "stage1_carrier", "stage2_carrier"}
    nominal = {p.name: p for p in build_parts(None, names)}
    actual = {p.name: p for p in build_parts(params, names)}

    def journal(part: Part) -> float:
        return float(max(f["diameter"] for f in cylindrical_features(part.solid)
                         if f["external"]))

    def bore(part: Part) -> float:
        return float(min(f["diameter"] for f in cylindrical_features(part.solid)
                         if not f["external"]))

    shaft, bearing, housing = actual["output_shaft"], actual["output_bearing_0"], actual["housing"]
    measured = {
        "output_shaft_diameter": journal(shaft),
        "bearing_bore_diameter": bore(bearing),
        "bearing_outer_diameter": journal(bearing),
    }
    # both bearing seats share one axis and diameter, so they are reported as one feature
    seats = [f for f in cylindrical_features(housing.solid)
             if not f["external"] and 12.0 < f["diameter"] < 30.0]
    if seats:
        measured["housing_seat_diameter"] = seats[0]["diameter"]
    holes = [f for f in cylindrical_features(housing.solid)
             if not f["external"] and f["diameter"] < 5.0]
    nom_holes = [f for f in cylindrical_features(nominal["housing"].solid)
                 if not f["external"] and f["diameter"] < 5.0]
    shift = (np.mean([h["axis_point"] for h in holes], axis=0)
             - np.mean([h["axis_point"] for h in nom_holes], axis=0))
    # Radial clearance comes from the cylinder diameters measured on the regenerated solids.
    # The bearing also touches the seat shoulder axially, so the overall minimum distance is
    # only meaningful for the shaft, which passes straight through the bearing.
    interfaces = {
        "shaft_to_bearing": {
            "radial_clearance_mm": (measured["bearing_bore_diameter"]
                                    - measured["output_shaft_diameter"]) / 2,
            "min_distance_mm": min_distance(shaft.solid, bearing.solid),
            "interference_mm3": interference_volume(shaft.solid, bearing.solid),
        },
        "bearing_to_housing": {
            "radial_clearance_mm": (measured.get("housing_seat_diameter", float("nan"))
                                    - measured["bearing_outer_diameter"]) / 2,
            "interference_mm3": interference_volume(bearing.solid, housing.solid),
        },
    }
    changes = []
    for name in sorted(names):
        dv = actual[name].solid.Volume() - nominal[name].solid.Volume()
        shift_com = (cq.Shape.centerOfMass(actual[name].solid)
                     - cq.Shape.centerOfMass(nominal[name].solid)).Length
        # a pin that moves keeps the volume but shifts the centre of mass
        if abs(dv) > 1e-9 or shift_com > 1e-9:
            changes.append({"component": name, "volume_change_mm3": float(dv),
                            "mass_change_kg": float(dv * actual[name].density * 1e-9),
                            "com_shift_mm": float(shift_com)})
    return {
        "level": "A",
        "regenerated_parameters": params,
        "measured_dimensions_mm": measured,
        # world X/Z correspond to the gearbox-local hole pattern axes
        "mount_pattern_shift_mm": {"x": float(shift[0]), "y": float(-shift[2])},
        "interfaces": interfaces,
        "changed_components": changes,
    }


# --------------------------------------------------------------------------- model file

_SRC = "MotionProof reference design - illustrative value, not a specification"


def _tol(tid: str, comp: str, param: str, char: str, cat: str, nominal: float, lo: float,
         hi: float, unit: str, dist: dict[str, Any], feature: str | None = None,
         datum: str | None = None, **extra: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": tid, "component": comp, "parameter": param, "characteristic": char,
        "category": cat, "nominal": nominal, "lower": lo, "upper": hi, "unit": unit,
        "distribution": dist, "source": _SRC, "confidence": "assumed"}
    if feature:
        d["feature"] = feature
    if datum:
        d["datum"] = datum
    return d | extra


def _tn(mean: float, std: float, lo: float, hi: float) -> dict[str, Any]:
    return {"type": "truncated_normal", "mean": mean, "std": std, "low": lo, "high": hi}


def reference_model_dict() -> dict[str, Any]:
    """The reference ``model.yaml`` content. All numbers are illustrative assumptions."""
    cyl: dict[str, Any] = {"kind": "cylinder", "direction": [0, 1, 0]}
    features: list[dict[str, Any]] = [
        {"id": "housing_axis", "component": "housing", "type": "datum_axis",
         "geometry": {"kind": "axis", "point": [0, 0, 0], "direction": [0, 1, 0]},
         "note": "gearbox axis"},
        {"id": "housing_mount_face", "component": "housing", "type": "datum_plane",
         "geometry": {"kind": "plane", "point": [0, -20, 0], "direction": [0, -1, 0]}},
        {"id": "output_shaft_journal", "component": "output_shaft", "type": "shaft",
         "nominal": {"diameter": 8.0}, "datum": "A", "mates_with": "bearing_bore",
         "geometry": {**cyl, "point": [0, 11, 0], "radius": 4.0, "length": 41.0}},
        {"id": "bearing_bore", "component": "output_bearing_0", "type": "bore",
         "nominal": {"diameter": 8.0},
         "geometry": {**cyl, "point": [0, 13, 0], "radius": 4.0, "length": 7.0}},
        {"id": "bearing_outer", "component": "output_bearing_0", "type": "shaft",
         "nominal": {"diameter": 22.0}, "mates_with": "housing_bearing_seat",
         "geometry": {**cyl, "point": [0, 13, 0], "radius": 11.0, "length": 7.0}},
        {"id": "housing_bearing_seat", "component": "housing", "type": "bearing_seat",
         "nominal": {"diameter": 22.0}, "datum": "A",
         "geometry": {**cyl, "point": [0, 13, 0], "radius": 11.0, "length": 7.0}},
        {"id": "input_shaft_journal", "component": "input_shaft", "type": "shaft",
         "nominal": {"diameter": 5.0}, "datum": "A",
         "geometry": {**cyl, "point": [0, -20, 0], "radius": 2.5, "length": 15.0}},
        {"id": "housing_ring_bore", "component": "housing", "type": "bore",
         "nominal": {"diameter": 34.0}, "datum": "A",
         "geometry": {**cyl, "point": [0, -18, 0], "radius": 17.0, "length": 30.0}},
        {"id": "mount_holes", "component": "housing", "type": "mounting_hole",
         "nominal": {"diameter": 3.2, "pattern_square": 31.0}, "datum": "B",
         "geometry": {**cyl, "point": [15.5, -20, 15.5], "radius": 1.6, "length": 4.0}},
        {"id": "stage1_carrier_pins", "component": "stage1_carrier", "type": "gear_interface",
         "nominal": {"pin_circle_radius": 8.25}, "datum": "A"},
        {"id": "stage2_carrier_pins", "component": "stage2_carrier", "type": "gear_interface",
         "nominal": {"pin_circle_radius": 9.0}, "datum": "A"},
        {"id": "output_joint", "component": "upper_arm_link", "type": "joint_interface",
         "datum": "A", "geometry": {"kind": "axis", "point": [0, 44, 0], "direction": [0, 1, 0]}},
    ]
    for f in features:
        f.setdefault("source", "reference design definition")
    two_pi = 6.283185307179586
    tol = [
        _tol("output_shaft_diameter", "output_shaft", "diameter", "diameter", "dimensional",
             8.0, -0.014, -0.005, "mm", _tn(7.9905, 0.0015, 7.986, 7.995),
             "output_shaft_journal", "A"),
        _tol("bearing_bore_diameter", "output_bearing_0", "bore diameter", "diameter",
             "dimensional", 8.0, -0.008, 0.0, "mm", _tn(7.996, 0.0013, 7.992, 8.0),
             "bearing_bore"),
        _tol("bearing_outer_diameter", "output_bearing_0", "outer diameter", "diameter",
             "dimensional", 22.0, -0.009, 0.0, "mm", _tn(21.9955, 0.0015, 21.991, 22.0),
             "bearing_outer"),
        _tol("housing_seat_diameter", "housing", "bearing seat diameter", "diameter",
             "dimensional", 22.0, 0.0, 0.021, "mm", _tn(22.0105, 0.0035, 22.0, 22.021),
             "housing_bearing_seat", "A"),
        _tol("bearing_internal_clearance", "output_bearing_0", "radial internal clearance",
             "radial_clearance", "assembly", 0.010, -0.007, 0.008, "mm",
             {"type": "uniform", "low": 0.003, "high": 0.018}),
        _tol("s1_backlash_sp", "stage1_sun", "sun-planet design backlash", "backlash",
             "assembly", 0.040, -0.015, 0.015, "mm", _tn(0.040, 0.005, 0.025, 0.055)),
        _tol("s1_backlash_pr", "stage1_ring", "planet-ring design backlash", "backlash",
             "assembly", 0.040, -0.015, 0.015, "mm", _tn(0.040, 0.005, 0.025, 0.055)),
        _tol("s2_backlash_sp", "stage2_sun", "sun-planet design backlash", "backlash",
             "assembly", 0.040, -0.015, 0.015, "mm", _tn(0.040, 0.005, 0.025, 0.055)),
        _tol("s2_backlash_pr", "stage2_ring", "planet-ring design backlash", "backlash",
             "assembly", 0.040, -0.015, 0.015, "mm", _tn(0.040, 0.005, 0.025, 0.055)),
        _tol("s1_planet_bearing_clearance", "stage1_carrier", "planet pin clearance",
             "radial_clearance", "assembly", 0.012, -0.007, 0.008, "mm",
             {"type": "uniform", "low": 0.005, "high": 0.020}),
        _tol("s2_planet_bearing_clearance", "stage2_carrier", "planet pin clearance",
             "radial_clearance", "assembly", 0.012, -0.007, 0.008, "mm",
             {"type": "uniform", "low": 0.005, "high": 0.020}),
        _tol("input_shaft_runout", "input_shaft", "runout (TIR)", "runout", "geometric",
             0.0, 0.0, 0.030, "mm", {"type": "uniform", "low": 0.0, "high": 0.030},
             "input_shaft_journal", "A"),
        _tol("input_shaft_runout_phase", "input_shaft", "runout phase", "phase", "geometric",
             0.0, 0.0, two_pi, "rad", {"type": "uniform", "low": 0.0, "high": two_pi},
             "input_shaft_journal", "A"),
        _tol("ring_offset_x", "housing", "ring bore position x", "position_x", "geometric",
             0.0, -0.03, 0.03, "mm", _tn(0.0, 0.010, -0.03, 0.03), "housing_ring_bore", "A",
             zone_group="ring_bore_position"),
        _tol("ring_offset_y", "housing", "ring bore position y", "position_y", "geometric",
             0.0, -0.03, 0.03, "mm", _tn(0.0, 0.010, -0.03, 0.03), "housing_ring_bore", "A",
             zone_group="ring_bore_position"),
        _tol("mount_hole_dx", "housing", "mounting pattern position x", "position_x",
             "geometric", 0.0, -0.05, 0.05, "mm", _tn(0.0, 0.017, -0.05, 0.05), "mount_holes",
             "B", zone_group="mount_position", correlation_group="housing_setup"),
        _tol("mount_hole_dy", "housing", "mounting pattern position y", "position_y",
             "geometric", 0.0, -0.05, 0.05, "mm", _tn(0.0, 0.017, -0.05, 0.05), "mount_holes",
             "B", zone_group="mount_position", correlation_group="housing_setup"),
        _tol("joint_axis_misalignment", "housing", "output axis perpendicularity",
             "perpendicularity", "geometric", 0.0, -0.05, 0.05, "deg",
             _tn(0.0, 0.017, -0.05, 0.05), "output_joint", "B"),
        _tol("gearbox_efficiency", "gearbox", "efficiency", "efficiency", "mechanical",
             0.81, -0.06, 0.06, "1", _tn(0.81, 0.02, 0.75, 0.87)),
        _tol("output_friction", "gearbox", "output Coulomb friction", "friction", "mechanical",
             0.05, -0.03, 0.05, "N*m", {"type": "uniform", "low": 0.02, "high": 0.10}),
        _tol("motor_torque_scale", "motor_body", "torque constant scatter", "torque_scale",
             "mechanical", 1.0, -0.10, 0.05, "1", _tn(1.0, 0.03, 0.90, 1.05)),
    ]
    for s in (1, 2):
        for k in range(3):
            tol.append(_tol(f"s{s}_pin_radial_{k}", f"stage{s}_carrier",
                            f"planet pin {k} radial position", "radial_position", "geometric",
                            0.0, -0.02, 0.02, "mm", _tn(0.0, 0.007, -0.02, 0.02),
                            f"stage{s}_carrier_pins", "A"))
    stages = []
    for s, st in enumerate(STAGES, start=1):
        inputs: dict[str, Any] = {
            "design_backlash_sun_planet": f"s{s}_backlash_sp",
            "design_backlash_planet_ring": f"s{s}_backlash_pr",
            "carrier_pin_radial": [f"s{s}_pin_radial_{k}" for k in range(3)],
            "planet_bearing_clearance": f"s{s}_planet_bearing_clearance",
            "ring_offset_x": "ring_offset_x", "ring_offset_y": "ring_offset_y",
        }
        if s == 1:
            inputs |= {"sun_runout": "input_shaft_runout",
                       "sun_runout_phase": "input_shaft_runout_phase"}
        stages.append({
            "id": st["id"], "joint": "shoulder", "order": s, "sun_teeth": st["sun"],
            "planet_teeth": st["planet"], "ring_teeth": st["ring"], "planets": 3,
            "module": st["module"], "pressure_angle": 20.0, "inputs": inputs})
    return {
        "schema": "motionproof.model/1",
        "name": "NEMA17 planetary joint - reference design",
        "description": "Synthetic reference assembly generated by MotionProof (CadQuery). "
                       "Not user hardware.",
        "synthetic": True,
        "source": {"kind": "reference_design", "generator": GENERATOR, "parameters": {}},
        "fidelity": "F2_reduced_order_dynamics",
        "features": features,
        "datums": [{"id": "A", "feature": "housing_axis", "type": "axis"},
                   {"id": "B", "feature": "housing_mount_face", "type": "plane"}],
        "tolerances": tol,
        "correlations": [{"parameters": ["mount_hole_dx", "mount_hole_dy"], "coefficient": 0.5,
                          "basis": "assumed",
                          "note": "both holes drilled in one setup (illustrative)"}],
        "fits": [
            {"id": "shaft_in_bearing", "shaft": "output_shaft_diameter",
             "bore": "bearing_bore_diameter", "role": "bearing_on_shaft", "joint": "shoulder",
             "max_interference": 0.006},
            {"id": "bearing_in_housing", "shaft": "bearing_outer_diameter",
             "bore": "housing_seat_diameter", "role": "bearing_in_housing", "joint": "shoulder"},
        ],
        "radial_supports": [{"joint": "shoulder", "bearing_span": BEARING_SPAN * 1e-3,
                             "internal_clearance": "bearing_internal_clearance",
                             "fits": ["shaft_in_bearing", "bearing_in_housing"]}],
        "gear_stages": stages,
        "drives": {"shoulder": {
            "motor": {"model": "generic NEMA 17 stepper (assumed values)",
                      "continuous_torque": 0.32, "peak_torque": 0.45, "max_speed": 157.0,
                      "torque_speed": [[0, 0.45], [31.4, 0.40], [62.8, 0.28], [104.7, 0.15],
                                       [157.0, 0.05]],
                      "rotor_inertia": 5.4e-6, "friction_torque": 0.004,
                      "source": "assumed representative values; replace with the datasheet",
                      "confidence": "assumed"},
            "gearbox": {"ratio": 33.0, "efficiency": 0.81, "backlash": 0.0,
                        "stiffness": 1500.0, "damping_ratio": 0.15,
                        "source": "33:1 is the target ratio (5.5 x 6 tooth counts); efficiency "
                                  "and stiffness are assumed", "confidence": "assumed"},
            "controller": {"bandwidth": 40.0},
            "friction": 0.05, "damping": 0.02}},
        "held_joints": {"elbow": 0.0},
        "effects": [
            {"tolerance": "gearbox_efficiency", "joint": "shoulder", "target": "efficiency",
             "mode": "set"},
            {"tolerance": "output_friction", "joint": "shoulder", "target": "friction",
             "mode": "set"},
            {"tolerance": "motor_torque_scale", "joint": "shoulder", "target": "torque_scale",
             "mode": "set"},
            {"tolerance": "joint_axis_misalignment", "joint": "shoulder", "target": "tilt_y"},
            {"tolerance": "mount_hole_dx", "joint": "shoulder", "target": "offset_x"},
            {"tolerance": "mount_hole_dy", "joint": "shoulder", "target": "offset_z"},
        ],
        "end_effector": {"body": "forearm", "offset": [0.35, 0.055, 0.0]},
        "simulation": {"timestep": 5e-4, "gravity": [0, 0, -9.81]},
        "assumptions": [
            "Synthetic geometry; gears are pitch cylinders, no tooth contact is simulated.",
            "All tolerances, motor data, efficiency and stiffness are illustrative assumptions.",
            "Backlash follows the documented planetary lost-motion relation (Fidelity 2).",
            "Radial play seats the output shaft in its worst-case position.",
            "The elbow is held by an ideal servo; only the shoulder drive train is modelled.",
            "Materials: aluminium 2700 kg/m^3 (links, housing), steel 7850 kg/m^3 (shafts).",
        ],
    }


def write_reference_project(directory: str | Path) -> Path:
    """Create a self-contained reference model folder; returns the path of ``model.yaml``."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    write_geometry(out / "geometry")
    path = out / "model.yaml"
    header = ("# SYNTHETIC REFERENCE DESIGN - generated by MotionProof, not user hardware.\n"
              "# Every numeric value below is an illustrative assumption.\n")
    path.write_text(header + yaml.safe_dump(reference_model_dict(), sort_keys=False),
                    encoding="utf-8")
    return path
