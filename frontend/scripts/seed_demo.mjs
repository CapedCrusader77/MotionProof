// Seed a demo workspace through the public API: project, reference design, one experiment run.
// Usage: node scripts/seed_demo.mjs http://127.0.0.1:8766
const base = (process.argv[2] ?? "http://127.0.0.1:8766") + "/api/v1";
const j = async (method, path, body) => {
  const r = await fetch(base + path, { method, headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(`${method} ${path}: ${r.status} ${await r.text()}`);
  return r.json();
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const wait = async (job) => {
  for (;;) {
    const s = await j("GET", `/jobs/${job.id}`);
    if (["completed", "failed", "cancelled"].includes(s.status)) return s;
    await sleep(1000);
  }
};

const project = await j("POST", "/projects", { name: "NEMA 17 planetary elbow",
  description: "Synthetic reference design: two-stage 33:1 planetary gearbox on a two-link arm." });
const model = await j("POST", "/models/reference", { project_id: project.id });
const cfg = {
  name: "Reversal about vertical, 0-0.5 kg payload",
  task: { type: "reversal", target: { shoulder: 1.5708 }, joint: "shoulder", payload_mass: 0.2 },
  sampling: { method: "monte_carlo", samples: 200, seed: 11 },
  operating: { payload_mass: { type: "uniform", low: 0.0, high: 0.5 } },
  constraints: [
    { name: "bidirectional_positioning", metric: "direction_error_ee", op: "<=", limit: 0.002 },
    { name: "torque", metric: "torque_utilisation_peak", op: "<=", limit: 0.8 },
    { name: "mesh_clearance", metric: "min_mesh_backlash_mm", op: ">=", limit: 0.0 },
  ],
};
const exp = await j("POST", "/experiments", { model_id: model.id, config: cfg });
const done = await wait(await j("POST", `/experiments/${exp.id}/run`));
console.log(JSON.stringify({ project: project.id, model: model.id, experiment: exp.id, status: done.status }));
