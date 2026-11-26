"""Validated data model for a MotionProof mechanical model (``model.yaml``).

Everything an experiment depends on is declared here: registered features and datums,
tolerance specifications with their distributions, fits, gear stages, per-joint drive trains
and the bindings that carry a manufacturing deviation into a physical model parameter.
Nothing is inferred silently; every entry carries its source and confidence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL_SCHEMA = "motionproof.model/1"

Vec3 = tuple[float, float, float]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Confidence(StrEnum):
    SPECIFIED = "specified"  # taken from a drawing / engineering specification
    MEASURED = "measured"  # derived from physical measurements
    ESTIMATED = "estimated"  # engineering estimate
    ASSUMED = "assumed"  # placeholder assumption, not evidence


class Fidelity(StrEnum):
    GEOMETRY = "F1_geometry_kinematics"
    REDUCED_ORDER = "F2_reduced_order_dynamics"


# --------------------------------------------------------------------------- distributions


class Uniform(_Model):
    type: Literal["uniform"] = "uniform"
    low: float
    high: float


class Normal(_Model):
    type: Literal["normal"] = "normal"
    mean: float
    std: float = Field(gt=0)


class TruncatedNormal(_Model):
    type: Literal["truncated_normal"] = "truncated_normal"
    mean: float
    std: float = Field(gt=0)
    low: float
    high: float


class LogNormal(_Model):
    """``exp(N(mu, sigma))``; ``mu`` and ``sigma`` describe the underlying normal."""

    type: Literal["lognormal"] = "lognormal"
    mu: float
    sigma: float = Field(gt=0)


class Discrete(_Model):
    type: Literal["discrete"] = "discrete"
    values: list[float] = Field(min_length=1)
    probabilities: list[float] | None = None


class Empirical(_Model):
    """Resamples the measured values through their empirical quantile function."""

    type: Literal["empirical"] = "empirical"
    samples: list[float] = Field(min_length=2)


Distribution = Annotated[
    Uniform | Normal | TruncatedNormal | LogNormal | Discrete | Empirical,
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- features


FeatureType = Literal[
    "shaft", "bore", "bearing_seat", "mounting_hole", "datum_plane", "datum_axis",
    "mating_face", "joint_interface", "gear_interface",
]


class GeometryReference(_Model):
    """Where a feature lives on its component, in component coordinates and source units."""

    kind: Literal["cylinder", "plane", "axis", "point", "none"] = "none"
    point: Vec3 | None = None
    direction: Vec3 | None = None
    radius: float | None = None
    length: float | None = None
    face_index: int | None = None  # index into the STEP face list, when detected from geometry


class Feature(_Model):
    id: str
    component: str
    type: FeatureType
    nominal: dict[str, float] = Field(default_factory=dict)
    unit: str = "mm"
    datum: str | None = None
    mates_with: str | None = None
    geometry: GeometryReference = GeometryReference()
    source: str = "manual"
    status: Literal["confirmed", "suggested"] = "confirmed"
    note: str | None = None


class Datum(_Model):
    id: str
    feature: str
    type: Literal["plane", "axis", "point"]


# --------------------------------------------------------------------------- tolerances

Characteristic = Literal[
    "length", "diameter", "thickness", "centre_distance", "gear_dimension",
    "position_x", "position_y", "radial_position", "runout", "concentricity", "phase",
    "parallelism", "perpendicularity", "angularity", "flatness", "circularity",
    "offset", "angular_misalignment", "radial_clearance", "axial_clearance",
    "backlash", "efficiency", "friction", "stiffness", "torque_scale", "other",
]

# characteristics that are stored but have no propagation model yet
UNPROPAGATED = {"flatness", "circularity"}


class ProcessData(_Model):
    """Optional process-capability data. Indices are only as good as these inputs."""

    mean: float
    std: float = Field(gt=0)
    sample_size: int | None = Field(default=None, ge=2)
    basis: Literal["measured", "assumed"] = "assumed"


class Tolerance(_Model):
    id: str
    component: str
    feature: str | None = None
    parameter: str
    characteristic: Characteristic = "other"
    category: Literal["dimensional", "geometric", "assembly", "mechanical"]
    nominal: float
    upper: float = Field(description="upper deviation from nominal (signed)")
    lower: float = Field(description="lower deviation from nominal (signed)")
    unit: str
    datum: str | None = None
    zone_group: str | None = Field(
        default=None, description="tolerances sharing a group form one circular zone"
    )
    distribution: Distribution
    correlation_group: str | None = None
    source: str
    confidence: Confidence
    verification: Literal["unverified", "measured", "inspected"] = "unverified"
    process: ProcessData | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _limits(self) -> Tolerance:
        if self.upper < self.lower:
            raise ValueError(f"tolerance {self.id!r}: upper deviation is below lower deviation")
        return self

    @property
    def lower_limit(self) -> float:
        return self.nominal + self.lower

    @property
    def upper_limit(self) -> float:
        return self.nominal + self.upper


class Correlation(_Model):
    """Pairwise correlation of the normal scores (Gaussian copula) of two tolerances."""

    parameters: tuple[str, str]
    coefficient: float = Field(ge=-1, le=1)
    basis: Literal["measured", "assumed"]
    note: str | None = None


# --------------------------------------------------------------------------- mechanics


class Fit(_Model):
    """A shaft/bore pair. ``clearance = bore - shaft`` (diametral)."""

    id: str
    shaft: str  # tolerance id of the shaft diameter
    bore: str  # tolerance id of the bore diameter
    role: Literal["generic", "bearing_on_shaft", "bearing_in_housing"] = "generic"
    joint: str | None = None  # joint whose radial play this fit contributes to
    max_interference: float | None = Field(
        default=None, ge=0, description="largest acceptable diametral interference, same unit"
    )
    min_clearance: float | None = None


class RadialSupport(_Model):
    """Bearing arrangement of an output shaft; turns radial play into offset and tilt."""

    joint: str
    bearing_span: float = Field(gt=0, description="distance between bearing rows, m")
    internal_clearance: str | None = None  # tolerance id (diametral bearing clearance)
    fits: list[str] = Field(default_factory=list)


class StageInputs(_Model):
    """Tolerance ids feeding a planetary stage. Any entry may be omitted (treated as nominal)."""

    design_backlash_sun_planet: str | None = None
    design_backlash_planet_ring: str | None = None
    carrier_pin_radial: list[str] = Field(default_factory=list)
    planet_bearing_clearance: str | None = None
    # diametral clearance of the planet pins in their carrier holes (a printed carrier, a
    # slip fit); adds to the planets' free travel like the bearing clearance
    carrier_pin_clearance: str | None = None
    # torsional play between the motor shaft and the sun (set screw, D flat, key), rad at the
    # sun; appears at the stage output divided by the stage ratio
    sun_coupling_play: str | None = None
    sun_runout: str | None = None
    sun_runout_phase: str | None = None
    ring_offset_x: str | None = None
    ring_offset_y: str | None = None


class PlanetaryStage(_Model):
    id: str
    joint: str
    order: int = Field(ge=1, description="1 = motor side")
    sun_teeth: int = Field(ge=6)
    planet_teeth: int = Field(ge=6)
    ring_teeth: int = Field(ge=12)
    planets: int = Field(ge=1, le=8)
    module: float = Field(gt=0, description="mm")
    pressure_angle: float = Field(default=20.0, gt=0, lt=45, description="degrees")
    inputs: StageInputs = StageInputs()

    @model_validator(mode="after")
    def _geometry(self) -> PlanetaryStage:
        if self.ring_teeth != self.sun_teeth + 2 * self.planet_teeth:
            raise ValueError(
                f"stage {self.id!r}: ring teeth must equal sun + 2*planet for standard gears"
            )
        if (self.sun_teeth + self.ring_teeth) % self.planets:
            raise ValueError(
                f"stage {self.id!r}: (sun + ring) teeth must be divisible by the planet count "
                "for equally spaced planets"
            )
        return self

    @property
    def ratio(self) -> float:
        """Sun input, carrier output, ring fixed."""
        return 1.0 + self.ring_teeth / self.sun_teeth

    @property
    def centre_distance(self) -> float:
        """Nominal sun-planet centre distance, mm."""
        return self.module * (self.sun_teeth + self.planet_teeth) / 2.0


class Motor(_Model):
    """Motor data. Torque in N*m at the shaft, speed in rad/s."""

    model: str | None = None
    continuous_torque: float = Field(gt=0)
    peak_torque: float = Field(gt=0)
    max_speed: float = Field(gt=0)
    # optional torque-speed curve: list of (speed rad/s, available torque N*m)
    torque_speed: list[tuple[float, float]] = Field(default_factory=list)
    rotor_inertia: float = Field(gt=0, description="kg*m^2")
    friction_torque: float = Field(default=0.0, ge=0)
    source: str
    confidence: Confidence

    @model_validator(mode="after")
    def _curve(self) -> Motor:
        speeds = [p[0] for p in self.torque_speed]
        if speeds != sorted(set(speeds)) or any(p[1] < 0 for p in self.torque_speed):
            raise ValueError("torque_speed must have strictly increasing speeds and "
                             "non-negative torques")
        return self


class Gearbox(_Model):
    ratio: float = Field(gt=0)
    efficiency: float = Field(gt=0, le=1)
    backlash: float = Field(default=0.0, ge=0, description="rad at the output, added to stages")
    stiffness: float = Field(gt=0, description="torsional stiffness at the output, N*m/rad")
    damping_ratio: float = Field(default=0.1, ge=0, description="of the rotor-on-spring mode")
    source: str
    confidence: Confidence


class Controller(_Model):
    """Motor-side PD with load feedforward; output-referred gains, derived from ``bandwidth``
    when ``None``."""

    bandwidth: float = Field(default=40.0, gt=0, description="rad/s")
    kp: float | None = None
    kd: float | None = None


class JointDrive(_Model):
    motor: Motor
    gearbox: Gearbox
    controller: Controller = Controller()
    friction: float = Field(default=0.0, ge=0, description="output Coulomb friction, N*m")
    damping: float = Field(default=0.0, ge=0, description="output viscous damping, N*m*s/rad")


EffectTarget = Literal[
    "backlash", "efficiency", "stiffness", "friction", "damping", "radial_play",
    "tilt_x", "tilt_y", "offset_x", "offset_y", "offset_z", "zero_offset", "torque_scale",
]


class Effect(_Model):
    """Reduced-order binding: carries a tolerance into a joint parameter (SI after conversion).

    ``add`` adds ``gain * (actual - nominal)``; ``set`` sets ``gain * actual``;
    ``scale`` multiplies by ``1 + gain * (actual - nominal)``.
    """

    tolerance: str
    joint: str
    target: EffectTarget
    mode: Literal["add", "set", "scale"] = "add"
    gain: float = 1.0


class Source(_Model):
    kind: Literal["reference_design", "mjcf", "urdf", "geometry"]
    generator: str | None = None
    file: str | None = None
    parameters: dict[str, float] = Field(default_factory=dict)


class EndEffector(_Model):
    body: str
    offset: Vec3 = (0.0, 0.0, 0.0)


class SimSettings(_Model):
    timestep: float = Field(default=2.5e-4, gt=0, le=5e-3)
    gravity: Vec3 = (0.0, 0.0, -9.81)


class MechanicalModelSpec(_Model):
    schema_version: str = Field(default=MODEL_SCHEMA, alias="schema")
    name: str
    description: str = ""
    synthetic: bool = Field(description="true when geometry is a generated reference design")
    source: Source
    fidelity: Fidelity = Fidelity.REDUCED_ORDER
    features: list[Feature] = Field(default_factory=list)
    datums: list[Datum] = Field(default_factory=list)
    tolerances: list[Tolerance] = Field(default_factory=list)
    correlations: list[Correlation] = Field(default_factory=list)
    fits: list[Fit] = Field(default_factory=list)
    radial_supports: list[RadialSupport] = Field(default_factory=list)
    gear_stages: list[PlanetaryStage] = Field(default_factory=list)
    drives: dict[str, JointDrive] = Field(default_factory=dict)
    held_joints: dict[str, float] = Field(
        default_factory=dict, description="joints held at a fixed angle by an ideal servo"
    )
    effects: list[Effect] = Field(default_factory=list)
    end_effector: EndEffector | None = None
    simulation: SimSettings = SimSettings()
    assumptions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _references(self) -> MechanicalModelSpec:
        if self.schema_version != MODEL_SCHEMA:
            raise ValueError(f"unsupported model schema {self.schema_version!r}")

        def unique(kind: str, ids: list[str]) -> set[str]:
            dup = sorted({i for i in ids if ids.count(i) > 1})
            if dup:
                raise ValueError(f"duplicate {kind} ids: {dup}")
            return set(ids)

        feats = unique("feature", [f.id for f in self.features])
        datums = unique("datum", [d.id for d in self.datums])
        tols = unique("tolerance", [t.id for t in self.tolerances])
        unique("fit", [f.id for f in self.fits])
        unique("gear stage", [g.id for g in self.gear_stages])

        def need(ref: str | None, pool: set[str], what: str, owner: str) -> None:
            if ref is not None and ref not in pool:
                raise ValueError(f"{owner} references unknown {what} {ref!r}")

        for d in self.datums:
            need(d.feature, feats, "feature", f"datum {d.id!r}")
        for f in self.features:
            need(f.datum, datums, "datum", f"feature {f.id!r}")
            need(f.mates_with, feats, "feature", f"feature {f.id!r}")
        for t in self.tolerances:
            need(t.feature, feats, "feature", f"tolerance {t.id!r}")
            need(t.datum, datums, "datum", f"tolerance {t.id!r}")
        for c in self.correlations:
            for p in c.parameters:
                need(p, tols, "tolerance", "correlation")
        for fit in self.fits:
            need(fit.shaft, tols, "tolerance", f"fit {fit.id!r}")
            need(fit.bore, tols, "tolerance", f"fit {fit.id!r}")
        fit_ids = {f.id for f in self.fits}
        for rs in self.radial_supports:
            need(rs.internal_clearance, tols, "tolerance", f"radial support {rs.joint!r}")
            for f_id in rs.fits:
                need(f_id, fit_ids, "fit", f"radial support {rs.joint!r}")
        for g in self.gear_stages:
            refs: list[str | None] = [
                v for k, v in g.inputs.model_dump().items() if k != "carrier_pin_radial"
            ]
            for r in [*refs, *g.inputs.carrier_pin_radial]:
                need(r, tols, "tolerance", f"gear stage {g.id!r}")
            if g.inputs.carrier_pin_radial and len(g.inputs.carrier_pin_radial) != g.planets:
                raise ValueError(f"gear stage {g.id!r}: one carrier_pin_radial entry per planet")
            need(g.joint, set(self.drives), "drive joint", f"gear stage {g.id!r}")
        for e in self.effects:
            need(e.tolerance, tols, "tolerance", "effect")
        return self

    def tolerance(self, tol_id: str) -> Tolerance:
        for t in self.tolerances:
            if t.id == tol_id:
                return t
        raise KeyError(f"no tolerance {tol_id!r}")


def model_json_schema() -> dict[str, Any]:
    return MechanicalModelSpec.model_json_schema(by_alias=True)
