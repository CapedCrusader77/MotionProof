# Python SDK

The same experiment as the web app and the CLI, from Python. This example is executed as a test
(`tests/integration/test_sdk_readme_example.py`), so it runs against the real implementation.

```python
from motionproof import MechanicalModel
from motionproof.experiments import ManufacturingExperiment
from motionproof.uncertainty import Uniform

model = MechanicalModel.load("demo/model.yaml")
experiment = ManufacturingExperiment(
    model=model,
    task={"type": "reversal", "joint": "shoulder", "target": {"shoulder": 1.5708}},
    samples=100,
    seed=42,
)
experiment.add_operating_variation("payload_mass", Uniform(0.0, 0.5))
experiment.add_constraint("lost_motion", "<=", 0.0065)
results = experiment.run()
print(results.failure_estimate)
print(results.sensitivity("lost_motion")[:5])
```

See [`docs/experiment-design.md`](experiment-design.md) for sampling designs and
[`docs/statistical-analysis.md`](statistical-analysis.md) for what `failure_estimate` and
`sensitivity` report.
