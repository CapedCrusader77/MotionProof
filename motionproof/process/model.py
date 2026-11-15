"""Process-aware manufacturing variation (statistical, explicitly parameterised).

This is not a machining simulation. A feature's dimension is modelled as

    x = target + drift(part index) + batch + setup + tool + part + measurement

where each term is a separate, user-supplied variance source that can be switched off. A
source declared ``shared_by`` a group of features is drawn *once* per batch / setup / tool and
added to every member, which is what makes dimensions cut in one setup move together.
No variance component is defaulted: a source that is not given is absent.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy import stats
from scipy.special import gammaln

Arr = NDArray[np.float64]
LEVELS = ("batch", "setup", "tool", "part", "measurement")
Level = Literal["batch", "setup", "tool", "part", "measurement"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(_M):
    """One variance source of one feature (standard deviation in the feature's unit)."""

    level: Level
    std: float = Field(ge=0)
    shared_group: str | None = Field(
        default=None, description="features naming the same group share one draw per level unit")
    enabled: bool = True
    basis: Literal["measured", "specified", "assumed"]


class Drift(_M):
    """Deterministic drift of the process mean with the part index inside a tool life."""

    kind: Literal["none", "linear", "piecewise", "measured"] = "none"
    rate: float = 0.0  # per part, linear
    breakpoints: list[tuple[int, float]] = Field(default_factory=list)  # (part index, offset)
    random_walk_std: float = Field(default=0.0, ge=0, description="per-part step, if justified")
    basis: Literal["measured", "specified", "assumed"] = "assumed"

    def offset(self, index: Arr) -> Arr:
        if self.kind == "linear":
            return self.rate * index
        if self.kind in ("piecewise", "measured"):
            if not self.breakpoints:
                return np.zeros_like(index, dtype=float)
            x = np.array([b[0] for b in self.breakpoints], dtype=float)
            y = np.array([b[1] for b in self.breakpoints], dtype=float)
            return np.asarray(np.interp(index, x, y), dtype=float)
        return np.zeros_like(index, dtype=float)


class FeatureProcess(_M):
    feature: str  # tolerance id this process produces
    process: str  # e.g. "CNC turning", "reaming", "FDM"
    target: float
    unit: str
    lower_limit: float
    upper_limit: float
    sources: list[Source] = Field(min_length=1)
    drift: Drift = Drift()

    @model_validator(mode="after")
    def _limits(self) -> FeatureProcess:
        if self.upper_limit <= self.lower_limit:
            raise ValueError(f"{self.feature}: upper limit must exceed lower limit")
        return self


class BatchPlan(_M):
    batches: int = Field(default=1, ge=1, le=1000)
    setups_per_batch: int = Field(default=1, ge=1, le=1000)
    parts_per_setup: int = Field(ge=1, le=100_000)
    tool_life_parts: int | None = Field(default=None, ge=1,
                                        description="tool changed (drift reset) every N parts")
    seed: int = 0


class ProcessModel(_M):
    name: str
    features: list[FeatureProcess] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> ProcessModel:
        ids = [f.feature for f in self.features]
        if len(set(ids)) != len(ids):
            raise ValueError("each feature may appear once in a process model")
        return self


def generate_batch(model: ProcessModel, plan: BatchPlan) -> dict[str, Any]:
    """Draw a virtual production batch. Returns per-part actual and measured values."""
    rng = np.random.default_rng(plan.seed)
    n = plan.batches * plan.setups_per_batch * plan.parts_per_setup
    if n > 2_000_000:
        raise ValueError("batch plan exceeds 2,000,000 parts")
    part = np.arange(n)
    batch = part // (plan.setups_per_batch * plan.parts_per_setup)
    setup = part // plan.parts_per_setup
    life = plan.tool_life_parts or n
    tool = part // life
    in_tool = (part % life).astype(float)
    unit_index = {"batch": batch, "setup": setup, "tool": tool, "part": part,
                  "measurement": part}
    shared: dict[tuple[str, str], Arr] = {}
    actual: dict[str, Arr] = {}
    measured: dict[str, Arr] = {}
    for f in model.features:
        x = f.target + f.drift.offset(in_tool)
        if f.drift.random_walk_std > 0:
            steps = rng.normal(0.0, f.drift.random_walk_std, n)
            walk = np.cumsum(steps)
            first = (part // life) * life  # index of the first part cut with the current tool
            x = x + walk - (walk[first] - steps[first])  # the walk restarts with each tool
        noise = np.zeros(n)
        for s in f.sources:
            if not s.enabled or s.std == 0:
                continue
            idx = unit_index[s.level]
            count = int(idx.max()) + 1
            if s.shared_group:
                key = (s.level, s.shared_group)
                if key not in shared:
                    shared[key] = rng.normal(0.0, 1.0, count)
                draw = shared[key] * s.std
            else:
                draw = rng.normal(0.0, s.std, count)
            if s.level == "measurement":
                noise = noise + draw[idx]
            else:
                x = x + draw[idx]
        actual[f.feature] = x
        measured[f.feature] = x + noise
    return {"parts": n, "batch": batch, "setup": setup, "tool": tool, "actual": actual,
            "measured": measured, "seed": plan.seed}


def batch_summary(model: ProcessModel, batch: dict[str, Any]) -> dict[str, Any]:
    """Distribution, capability and out-of-specification share of every feature."""
    out: dict[str, Any] = {}
    for f in model.features:
        x = batch["actual"][f.feature]
        mean, std = float(x.mean()), float(x.std(ddof=1))
        oos = (x < f.lower_limit) | (x > f.upper_limit)
        out[f.feature] = {
            "process": f.process, "unit": f.unit, "mean": mean, "std": std,
            "min": float(x.min()), "max": float(x.max()),
            "cp": (f.upper_limit - f.lower_limit) / (6 * std) if std > 0 else None,
            "cpk": min(f.upper_limit - mean, mean - f.lower_limit) / (3 * std)
            if std > 0 else None,
            "out_of_spec": int(oos.sum()), "out_of_spec_fraction": float(oos.mean()),
            "note": "overall capability from all enabled sources (long-term, Pp/Ppk sense)",
        }
    return out


def variance_components(values: Arr, batch: Arr, setup: Arr) -> dict[str, Any]:
    """Method-of-moments estimate for a balanced nested design: batch > setup > part.

    Returns standard deviations. A negative moment estimate is reported as zero with a note,
    which is the usual sign that the component cannot be distinguished from the data.
    """
    values = np.asarray(values, dtype=float)
    b_ids, s_ids = np.unique(batch), np.unique(setup)
    a = len(b_ids)
    n_setups = len(s_ids)
    b = n_setups // a
    n = len(values) // n_setups
    if a * b != n_setups or n_setups * n != len(values) or n < 2:
        raise ValueError("variance components need a balanced design with at least two parts "
                         "per setup")
    grid = values.reshape(a, b, n)
    setup_mean = grid.mean(axis=2)
    batch_mean = setup_mean.mean(axis=1)
    grand = float(batch_mean.mean())
    ms_within = float(((grid - setup_mean[:, :, None]) ** 2).sum() / (a * b * (n - 1)))
    notes: list[str] = []
    var_setup = var_batch = 0.0
    if b >= 2:
        ms_setup = float(n * ((setup_mean - batch_mean[:, None]) ** 2).sum() / (a * (b - 1)))
        var_setup = (ms_setup - ms_within) / n
    else:
        ms_setup = ms_within
        notes.append("one setup per batch: setup and batch variation cannot be separated; "
                     "the batch figure contains both")
    if a >= 2:
        ms_batch = float(b * n * ((batch_mean - grand) ** 2).sum() / (a - 1))
        var_batch = (ms_batch - ms_setup) / (b * n)
    else:
        notes.append("a single batch: batch-to-batch variation cannot be estimated")
    if 2 <= a < 10:
        notes.append(f"only {a} batches: the batch standard deviation rests on {a - 1} "
                     "degrees of freedom and is imprecise")
    for name, v in (("setup", var_setup), ("batch", var_batch)):
        if v < 0:
            notes.append(f"{name} component estimate is negative; reported as zero")
    return {"mean": grand, "part_std": float(np.sqrt(ms_within)),
            "setup_std": float(np.sqrt(max(var_setup, 0.0))),
            "batch_std": float(np.sqrt(max(var_batch, 0.0))),
            "batches": a, "setups_per_batch": b, "parts_per_setup": n, "notes": notes,
            "method": "balanced nested ANOVA, method of moments"}


def control_chart(values: Arr, subgroup: int) -> dict[str, Any]:
    """X-bar / S limits from rational subgroups, plus simple run and trend checks.

    Signals are reported; their absence is not a proof of statistical stability.
    """
    values = np.asarray(values, dtype=float)
    k = len(values) // subgroup
    if subgroup < 2 or k < 5:
        raise ValueError("a control chart needs subgroups of at least 2 and at least 5 of them")
    g = values[: k * subgroup].reshape(k, subgroup)
    xbar, s = g.mean(axis=1), g.std(axis=1, ddof=1)
    c4 = float(np.sqrt(2 / (subgroup - 1)) * np.exp(
        gammaln(subgroup / 2) - gammaln((subgroup - 1) / 2)))
    sigma = float(s.mean() / c4)
    centre = float(xbar.mean())
    half = 3 * sigma / np.sqrt(subgroup)
    beyond = np.flatnonzero(np.abs(xbar - centre) > half)
    side = np.sign(xbar - centre)
    run = longest = 0
    for i in range(k):
        run = run + 1 if i and side[i] == side[i - 1] and side[i] != 0 else 1
        longest = max(longest, run)
    slope, _, _, p_trend, _ = stats.linregress(np.arange(k), xbar)
    signals = []
    if len(beyond):
        signals.append(f"{len(beyond)} subgroup means beyond the 3-sigma limits")
    if longest >= 9:  # Nelson rule 2
        signals.append(f"run of {longest} consecutive subgroup means on one side of the centre")
    if p_trend < 0.01:
        signals.append(f"trend in subgroup means: slope {slope:.3g} per subgroup "
                       f"(p = {p_trend:.2g})")
    return {"subgroups": k, "subgroup_size": subgroup, "centre": centre,
            "ucl": centre + half, "lcl": centre - half, "sigma_within": sigma,
            "xbar": xbar.tolist(), "s": s.tolist(), "beyond_limits": beyond.tolist(),
            "longest_run": int(longest), "trend_slope": float(slope),
            "trend_p_value": float(p_trend), "signals": signals,
            "statement": "signals found: the process is not in statistical control"
            if signals else "no signal from these rules in this data; this alone does not "
                            "establish that the process is stable"}


def fit_linear_drift(values: Arr) -> dict[str, float]:
    """Least-squares drift rate per part from an ordered measurement series."""
    values = np.asarray(values, dtype=float)
    res = stats.linregress(np.arange(len(values)), values)
    return {"rate": float(res.slope), "rate_std_error": float(res.stderr),
            "intercept": float(res.intercept), "p_value": float(res.pvalue)}


def variant_rows(batch: dict[str, Any], indices: Arr | None = None) -> list[dict[str, float]]:
    """Per-part tolerance values, ready for ``MechanicalModel.variant``."""
    idx = np.arange(batch["parts"]) if indices is None else np.asarray(indices)
    return [{k: float(v[i]) for k, v in batch["actual"].items()} for i in idx]
