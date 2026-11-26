"""Predictions written down before the hardware is measured, and the check against them.

A prediction made after seeing the measurement can always be made to fit. So the rig test is
split in two: ``predict`` simulates the test on many virtual copies of the model drawn from its
tolerances, and writes the predicted range of the measured quantity, the acceptance rule and a
hash of all of it to a file. Commit that file to version control *before* measuring; the commit
date is the evidence that the prediction came first. ``check`` then reads the measured analysis
(``motionproof hardware analyse``) and applies the rule unchanged.

Only lost motion on a reversal is predicted for now: it is the quantity the drive-train model
is about, and the analysis measures it without using the model.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import numpy as np

from motionproof.experiments.runner import versions
from motionproof.hardware.device import HardwareTest
from motionproof.model import MechanicalModel
from motionproof.tolerances.sampling import VariableSpace

SCHEMA = "motionproof.hardware-prediction/1"
QUANTILES = (0.05, 0.95)


class PredictionError(ValueError):
    pass


def _digest(body: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def predict(model: MechanicalModel, test: HardwareTest, samples: int = 64, seed: int = 0,
            margin: float = 0.0) -> dict[str, Any]:
    """Predict the lost motion the rig will measure.

    The interval is the 5 to 95 % range over ``samples`` virtual copies of the model; the
    measurement passes if it falls inside the interval widened by ``margin`` (rad) on each side,
    which should cover the encoder resolution. Raises if the model cannot simulate the test."""
    if test.kind != "reversal":
        raise PredictionError("only reversal tests have a predicted quantity (lost motion)")
    if samples < 20:
        raise PredictionError("use at least 20 samples for a 5 to 95 % range")
    if margin < 0:
        raise PredictionError("the margin cannot be negative")
    space = VariableSpace.from_model(model.spec)
    design = space.design("monte_carlo", samples, seed)
    task = test.task()
    nominal = model.engine.run(model.variant({}), task, keep_trace=False)
    if not nominal.valid:
        raise PredictionError(f"the nominal simulation is invalid: {nominal.message}")
    values: list[float] = []
    invalid = 0
    for row in design.values:
        res = model.engine.run(model.variant(dict(zip(space.names, row, strict=True))), task,
                               keep_trace=False)
        lm = res.metrics.get("lost_motion") if res.valid else None
        if lm is None or not np.isfinite(lm):
            invalid += 1
        else:
            values.append(float(lm))
    if len(values) < 0.9 * samples:
        raise PredictionError(f"{invalid} of {samples} virtual copies could not be simulated; "
                              "fix the model before predicting")
    low, high = (float(np.quantile(values, q)) for q in QUANTILES)
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": {"name": model.spec.name, "synthetic": model.spec.synthetic,
                  "fingerprint": model.fingerprint},
        "test": test.model_dump(),
        "quantity": "lost_motion",
        "unit": "rad",
        "nominal": float(nominal.metrics["lost_motion"]),
        "interval": [low, high],
        "interval_rule": f"{QUANTILES[0]:.0%} to {QUANTILES[1]:.0%} of {len(values)} virtual "
                         f"copies drawn from the model's tolerances (seed {seed})",
        "margin": margin,
        "acceptance": "PASS if every measured lost motion lies within "
                      "[interval low - margin, interval high + margin]",
        "invalid_copies": invalid,
        "versions": versions(),
    }
    return body | {"sha256": _digest(body)}


def check(prediction: dict[str, Any], analyses: list[dict[str, Any]],
          model: MechanicalModel | None = None) -> dict[str, Any]:
    """Apply a prediction's acceptance rule to one or more measured analyses."""
    if prediction.get("schema") != SCHEMA:
        raise PredictionError("not a MotionProof hardware prediction file")
    body = {k: v for k, v in prediction.items() if k != "sha256"}
    if _digest(body) != prediction.get("sha256"):
        raise PredictionError("the prediction file was changed after it was written")
    if model is not None and model.fingerprint != prediction["model"]["fingerprint"]:
        raise PredictionError("the model has changed since the prediction was made; compare "
                              "with the model that made it")
    if not analyses:
        raise PredictionError("give at least one measured analysis")
    low = prediction["interval"][0] - prediction["margin"]
    high = prediction["interval"][1] + prediction["margin"]
    runs = []
    for i, a in enumerate(analyses):
        test = a.get("test")
        if test != prediction["test"]:
            raise PredictionError(f"analysis {i + 1} is of a different test than the one "
                                  "predicted")
        if "lost_motion" not in a:
            raise PredictionError(f"analysis {i + 1} has no measured lost motion")
        m = float(a["lost_motion"])
        runs.append({"measured": m, "inside": low <= m <= high})
    ok = all(r["inside"] for r in runs)
    return {"status": "PASS" if ok else "FAIL", "accepted_range": [low, high],
            "nominal": prediction["nominal"], "runs": runs,
            "prediction_created": prediction["created"], "prediction_sha256": prediction["sha256"],
            "statement": "Measured against a prediction recorded beforehand. The order is only "
                         "established if the prediction file was committed before measuring."}
