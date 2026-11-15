"""Rigid-body transform maths (NumPy only). Quaternions use MuJoCo's (w, x, y, z) order."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

Mat = NDArray[np.float64]


def normalize(v: ArrayLike) -> Mat:
    a = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(a))
    if n < 1e-12:
        raise ValueError("cannot normalise a zero-length vector")
    return a / n


def skew(v: ArrayLike) -> Mat:
    x, y, z = np.asarray(v, dtype=float)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def axis_angle_matrix(axis: ArrayLike, angle: float) -> Mat:
    """Rodrigues rotation matrix for a rotation of ``angle`` rad about ``axis``."""
    k = skew(normalize(axis))
    return np.asarray(np.eye(3) + np.sin(angle) * k + (1.0 - np.cos(angle)) * (k @ k),
                      dtype=float)


def quat_to_matrix(q: ArrayLike) -> Mat:
    w, x, y, z = normalize(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def matrix_to_quat(r: ArrayLike) -> Mat:
    """Rotation matrix to unit quaternion (w, x, y, z) with w >= 0."""
    m = np.asarray(r, dtype=float)
    t = float(np.trace(m))
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        q = np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s,
                      (m[1, 0] - m[0, 1]) / s])
    else:
        i = int(np.argmax(np.diag(m)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = np.sqrt(1.0 + m[i, i] - m[j, j] - m[k, k]) * 2
        q = np.zeros(4)
        q[0] = (m[k, j] - m[j, k]) / s
        q[1 + i] = 0.25 * s
        q[1 + j] = (m[j, i] + m[i, j]) / s
        q[1 + k] = (m[k, i] + m[i, k]) / s
    q = q / np.linalg.norm(q)
    return np.asarray(-q if q[0] < 0 else q, dtype=float)


def quat_multiply(a: ArrayLike, b: ArrayLike) -> Mat:
    aw, ax, ay, az = np.asarray(a, dtype=float)
    bw, bx, by, bz = np.asarray(b, dtype=float)
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ]
    )


def make_transform(rotation: ArrayLike | None = None, translation: ArrayLike | None = None) -> Mat:
    t = np.eye(4)
    if rotation is not None:
        t[:3, :3] = np.asarray(rotation, dtype=float)
    if translation is not None:
        t[:3, 3] = np.asarray(translation, dtype=float)
    return t


def invert_transform(t: ArrayLike) -> Mat:
    m = np.asarray(t, dtype=float)
    out = np.eye(4)
    out[:3, :3] = m[:3, :3].T
    out[:3, 3] = -m[:3, :3].T @ m[:3, 3]
    return out


def transform_point(t: ArrayLike, p: ArrayLike) -> Mat:
    m = np.asarray(t, dtype=float)
    return np.asarray(m[:3, :3] @ np.asarray(p, dtype=float) + m[:3, 3], dtype=float)


def transform_vector(t: ArrayLike, v: ArrayLike) -> Mat:
    return np.asarray(np.asarray(t, dtype=float)[:3, :3] @ np.asarray(v, dtype=float),
                      dtype=float)


def is_rotation(r: ArrayLike, tol: float = 1e-6) -> bool:
    m = np.asarray(r, dtype=float)
    return bool(
        m.shape == (3, 3)
        and np.allclose(m @ m.T, np.eye(3), atol=tol)
        and abs(np.linalg.det(m) - 1.0) < tol
    )


def rotation_error(r_a: ArrayLike, r_b: ArrayLike) -> Mat:
    """Rotation vector (axis * angle, world frame) taking ``r_a`` to ``r_b``."""
    r = np.asarray(r_b, dtype=float) @ np.asarray(r_a, dtype=float).T
    cos = np.clip((np.trace(r) - 1.0) / 2.0, -1.0, 1.0)
    angle = float(np.arccos(cos))
    if angle < 1e-9:
        return np.zeros(3)
    w = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
    if abs(np.pi - angle) < 1e-6:  # near 180 deg the antisymmetric part vanishes
        axis = np.sqrt(np.clip((np.diag(r) + 1.0) / 2.0, 0.0, None))
        i = int(np.argmax(axis))
        signs = np.sign(r[i] + 1e-300)
        signs[i] = 1.0
        return np.asarray(axis * signs * angle, dtype=float)
    return np.asarray(w / (2.0 * np.sin(angle)) * angle, dtype=float)


# ---- inertia -----------------------------------------------------------------

def parallel_axis(inertia_com: ArrayLike, mass: float, offset: ArrayLike) -> Mat:
    """Inertia about a point displaced by ``offset`` from the centre of mass."""
    d = np.asarray(offset, dtype=float)
    return np.asarray(inertia_com, dtype=float) + mass * (float(d @ d) * np.eye(3) - np.outer(d, d))


def rotate_inertia(inertia: ArrayLike, rotation: ArrayLike) -> Mat:
    r = np.asarray(rotation, dtype=float)
    return np.asarray(r @ np.asarray(inertia, dtype=float) @ r.T, dtype=float)


def combine_inertias(
    parts: list[tuple[float, Mat, Mat]],
) -> tuple[float, Mat, Mat]:
    """Combine rigid parts given as (mass, com, inertia_about_own_com) in one common frame.

    Returns (total mass, combined com, combined inertia about the combined com).
    """
    total = float(sum(m for m, _, _ in parts))
    if total <= 0:
        return 0.0, np.zeros(3), np.zeros((3, 3))
    com = sum((m * np.asarray(c, dtype=float) for m, c, _ in parts), np.zeros(3)) / total
    inertia = np.zeros((3, 3))
    for m, c, i_c in parts:
        inertia += parallel_axis(i_c, m, np.asarray(c, dtype=float) - com)
    return total, com, inertia


def inertia_is_physical(inertia: ArrayLike, tol: float = 1e-9) -> bool:
    """Symmetric, positive-definite and principal moments satisfy the triangle inequality."""
    m = np.asarray(inertia, dtype=float)
    if not np.allclose(m, m.T, atol=tol * max(1.0, float(np.abs(m).max()))):
        return False
    w = np.linalg.eigvalsh((m + m.T) / 2)
    if w[0] <= 0:
        return False
    slack = tol * w[2]
    return bool(w[0] + w[1] >= w[2] - slack)
