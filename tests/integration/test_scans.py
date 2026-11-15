"""As-built import: every case uses SYNTHETIC scans with known ground truth."""

from __future__ import annotations

from pathlib import Path

import cadquery as cq
import numpy as np
import pytest
import trimesh

from motionproof.core.schema import MechanicalModelSpec
from motionproof.manufacturing.variants import nominal_values, resolve_variant
from motionproof.reference.nema17_arm import reference_model_dict
from motionproof.scans import inspection as I
from motionproof.scans import pointcloud as P
from motionproof.scans import registration as R
from motionproof.scans import synthetic as S

NOMINAL_D, LENGTH = 8.0, 40.0


@pytest.fixture(scope="module")
def shaft() -> R.Nominal:
    mesh = trimesh.creation.cylinder(radius=NOMINAL_D / 2, height=LENGTH, sections=720)
    mesh.apply_translation([0, 0, LENGTH / 2])
    return R.Nominal.from_mesh(mesh, "nominal shaft", count=150_000, seed=1)


def test_shaft_diameter_deviation_is_recovered_and_used_downstream(shaft: R.Nominal) -> None:
    """Acceptance test: +30 um on diameter, 5 um noise, unknown pose.

    Accepted error on the recovered diameter: 2 um (noise 5 um over 20,000 points)."""
    true_d = 8.030
    pts = S.cylinder_scan(true_d, LENGTH, 20_000, noise=0.005, seed=3)
    moved, _ = S.rigid(pts, (0.3, 1.0, 0.2), 0.02, (0.4, -0.3, 0.2))
    cloud = P.PointCloud(moved, units="mm")
    reg = R.icp(cloud.in_mm(), shaft, init=R.coarse_align(cloud.in_mm(), shaft),
                noise=P.noise_estimate(cloud), lock=("rz",))
    assert reg.converged and reg.valid_for_inspection, reg.diagnostics
    aligned = reg.apply(cloud.in_mm())
    mask = I.select_near_cylinder(aligned, np.zeros(3), np.array([0, 0, 1.0]), NOMINAL_D / 2,
                                  band=0.2, start=1.0, length=LENGTH - 2.0)
    fit = I.fit_cylinder(aligned[mask], np.array([0, 0, 1.0]))
    assert fit.diameter == pytest.approx(true_d, abs=0.002)
    assert fit.diameter_std_error < 0.001 and fit.arc_coverage_deg > 350
    dev = I.deviation(aligned[mask], shaft)
    assert dev["mean"] == pytest.approx((true_d - NOMINAL_D) / 2, abs=0.002)

    # downstream: the approved measurement replaces the sampled dimension in the fit analysis
    spec = MechanicalModelSpec.model_validate(reference_model_dict())
    m = I.MeasuredFeature("M1", "output_shaft_journal", "diameter", fit.diameter, "mm",
                          fit.diameter_std_error, "least-squares cylinder", "synthetic scan",
                          "icp", tolerance="output_shaft_diameter")
    assert I.as_built_values(spec, [m])["values"] == {}  # not approved yet: not used
    m.status = "approved"
    built = I.as_built_values(spec, [m])
    assert built["used"][0]["in_spec"] is False  # 8.030 is above the 7.995 upper limit
    variant = resolve_variant(spec, nominal_values(spec) | built["values"])
    fit_res = next(f for f in variant.fits if f.fit == "shaft_in_bearing")
    assert fit_res.state == "interference"
    assert fit_res.clearance == pytest.approx(8.0 - fit.diameter)
    assert any(v["subject"] == "shaft_in_bearing" for v in variant.violations)


def test_known_pose_is_recovered_on_an_asymmetric_part() -> None:
    part = (cq.Workplane("XY").box(60, 40, 10)
            .union(cq.Workplane("XY").box(10, 40, 30).translate((25, 0, 20)))
            .faces(">Z").workplane().pushPoints([(-15, 8)]).hole(6.0))
    verts, faces = part.val().tessellate(0.01, 0.1)
    mesh = trimesh.Trimesh([v.toTuple() for v in verts], faces, process=False)
    nominal = R.Nominal.from_mesh(mesh, "bracket", 150_000, seed=0)
    scan, _ = trimesh.sample.sample_surface(mesh, 15_000, seed=5)
    moved, applied = S.rigid(np.asarray(scan), (0.2, 0.4, 1.0), 0.15, (3.0, -2.0, 1.5))
    reg = R.icp(moved, nominal, init=R.coarse_align(moved, nominal), accept_rms=0.05)
    assert reg.valid_for_inspection, reg.diagnostics
    recovered = np.asarray(reg.transform) @ applied
    assert np.allclose(recovered, np.eye(4), atol=5e-3)
    assert reg.rms < 0.02
    assert any("unconstrained" in d for d in reg.diagnostics)


def test_datum_alignment_and_locked_degrees_of_freedom(shaft: R.Nominal) -> None:
    pts = S.cylinder_scan(NOMINAL_D, LENGTH, 12_000, seed=2)
    moved, applied = S.rigid(pts, (1.0, 0.0, 0.0), 0.4, (5.0, 2.0, -3.0))
    end = moved[: 0]  # the end face is selected below through the known applied pose
    back = (moved - applied[:3, 3]) @ applied[:3, :3]
    end = moved[np.abs(back[:, 2]) < 1e-9]
    origin, normal, rms = R.fit_plane(end)
    assert rms < 1e-9
    side = moved[(back[:, 2] > 1) & (back[:, 2] < LENGTH - 1)]
    axis = np.asarray(I.fit_cylinder(side).axis_direction)
    if float(axis @ (side.mean(axis=0) - origin)) < 0:
        axis = -axis
    scan_frame = R.datum_frame(axis, np.array([1.0, 0.3, 0.2]), origin)
    nominal_frame = R.datum_frame(np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), np.zeros(3))
    init = R.align_by_datums(scan_frame, nominal_frame)
    reg = R.icp(moved, shaft, init=init, lock=("rx", "ry", "rz", "tz"), accept_rms=0.05)
    t = np.asarray(reg.transform)
    assert np.allclose(t[:3, :3], init[:3, :3]) and t[2, 3] == pytest.approx(init[2, 3])
    assert reg.valid_for_inspection and reg.locked == ["rx", "ry", "rz", "tz"]
    with pytest.raises(P.ScanError, match="unknown degrees"):
        R.icp(moved, shaft, lock=("yaw",))


def test_cleaning_outliers_duplicates_and_downsampling() -> None:
    pts = S.cylinder_scan(10.0, 30.0, 6000, noise=0.004, seed=1, outliers=60)
    cloud = P.PointCloud(np.concatenate([pts, pts[:500]]), units="mm")
    deduped = P.remove_duplicates(cloud)
    assert len(deduped) == len(pts)
    cleaned = P.remove_outliers(deduped)
    removed = len(deduped) - len(cleaned)
    assert 40 <= removed <= 200  # the 60 planted outliers, few surface points
    radial = np.linalg.norm(cleaned.points[:, :2], axis=1)
    assert np.mean(radial > 5.5) < 0.003
    thin = P.voxel_downsample(cleaned, 1.0)
    assert len(thin) < len(cleaned) / 3 and "voxel" in thin.history[-1]
    assert 0.001 < P.noise_estimate(cleaned) < 0.02


def test_incomplete_scan_reports_missing_coverage_and_weak_fit(shaft: R.Nominal) -> None:
    half = S.cylinder_scan(NOMINAL_D, LENGTH, 8000, seed=4, arc_deg=90.0, ends=False)
    dev = I.deviation(half, shaft)
    assert 0.15 < dev["coverage"]["fraction_of_nominal_surface"] < 0.30
    assert len(dev["missing"]) > 0 and abs(dev["mean"]) < 1e-3
    fit = I.fit_cylinder(half, np.array([0, 0, 1.0]))
    assert fit.arc_coverage_deg == pytest.approx(90, abs=3)
    assert any("poorly constrained" in w for w in fit.warnings)


def test_wrong_geometry_is_not_accepted_as_an_inspection(shaft: R.Nominal) -> None:
    box = trimesh.creation.box(extents=(20, 12, 30))
    pts, _ = trimesh.sample.sample_surface(box, 8000, seed=0)
    reg = R.icp(np.asarray(pts), shaft, init=R.coarse_align(np.asarray(pts), shaft),
                accept_rms=0.05)
    assert reg.valid_for_inspection is False
    assert any("exceeds the acceptance threshold" in d for d in reg.diagnostics)


def test_units_are_never_assumed(tmp_path: Path, shaft: R.Nominal) -> None:
    pts = S.cylinder_scan(0.8, 4.0, 3000, seed=0, ends=False)  # scanned in centimetres
    path = S.write_xyz(tmp_path / "synthetic_shaft_cm.xyz", pts, "cm", "8 mm shaft in cm")
    cloud = P.read_point_cloud(path)
    assert cloud.units is None
    with pytest.raises(P.ScanError, match="no length unit"):
        cloud.in_mm()
    cloud = P.read_point_cloud(path, units="cm")
    fit = I.fit_cylinder(cloud.in_mm(), np.array([0, 0, 1.0]))
    assert fit.diameter == pytest.approx(8.0, abs=1e-4)
    with pytest.raises(ValueError, match="synthetic"):
        S.write_xyz(tmp_path / "shaft.xyz", pts, "cm", "x")


def test_readers_csv_pcd_ply_and_errors(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    pts = rng.normal(size=(200, 3))
    nrm = pts / np.linalg.norm(pts, axis=1, keepdims=True)
    csv_path = tmp_path / "scan.csv"
    np.savetxt(csv_path, np.hstack([pts, nrm, rng.uniform(0, 1, (200, 1))]), delimiter=",",
               header="x,y,z,nx,ny,nz,confidence", comments="")
    c = P.read_point_cloud(csv_path, units="mm", meta={"scanner": "test"})
    assert len(c) == 200 and c.normals is not None and c.confidence is not None
    assert np.allclose(c.points, pts, atol=1e-6) and c.meta["scanner"] == "test"

    pcd = tmp_path / "scan.pcd"
    pcd.write_text("# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\n"
                   "COUNT 1 1 1\nWIDTH 200\nHEIGHT 1\nPOINTS 200\nDATA ascii\n"
                   + "\n".join(" ".join(f"{v:.6f}" for v in p) for p in pts), encoding="utf-8")
    assert np.allclose(P.read_point_cloud(pcd).points, pts, atol=1e-5)
    binary = tmp_path / "bin.pcd"
    binary.write_text("VERSION 0.7\nFIELDS x y z\nDATA binary\n", encoding="utf-8")
    with pytest.raises(P.ScanError, match="only ASCII PCD"):
        P.read_point_cloud(binary)

    ply = tmp_path / "scan.ply"
    trimesh.PointCloud(pts).export(str(ply))
    assert len(P.read_point_cloud(ply)) == 200
    stl = tmp_path / "mesh.stl"
    trimesh.creation.box(extents=(1, 2, 3)).export(str(stl))
    m = P.read_point_cloud(stl, units="mm")
    assert m.normals is not None and "not raw scan data" in m.history[0]

    bad = tmp_path / "bad.xyz"
    bad.write_text("1 2 3\n4 5\n6 7 8\n", encoding="utf-8")
    with pytest.raises(P.ScanError, match="differing numbers of columns"):
        P.read_point_cloud(bad)
    with pytest.raises(P.ScanError, match="unsupported scan format"):
        P.read_point_cloud(csv_path.rename(tmp_path / "scan.e57"))


def test_feature_measurements_between_cylinders() -> None:
    a = S.cylinder_scan(6.0, 10.0, 4000, seed=1, ends=False)
    b = S.cylinder_scan(6.0, 10.0, 4000, seed=2, ends=False) + np.array([31.02, 0.0, 0.0])
    fa, fb = (I.fit_cylinder(p, np.array([0, 0, 1.0])) for p in (a, b))
    assert I.centre_distance(fa, fb) == pytest.approx(31.02, abs=1e-6)
    off = I.axis_offset(fb, np.array([31.0, 0, 0]), np.array([0, 0, 1.0]))
    assert off["eccentricity"] == pytest.approx(0.02, abs=1e-6) and off["tilt_rad"] < 1e-6
    plane = np.column_stack([np.random.default_rng(0).uniform(-5, 5, (500, 2)),
                             0.01 * np.where(np.arange(500) % 2, 1.0, -1.0)])
    # the fitted plane tilts slightly with 500 random points, adding up to ~10 % to the range
    assert I.flatness(plane)["range"] == pytest.approx(0.02, rel=0.10)
