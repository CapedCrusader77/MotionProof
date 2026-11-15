# API reference

Base path `/api/v1`. Interactive documentation: `/docs` on the running server. Errors are JSON
`{"error": "message"}` with status 404, 409, 413 or 422.

| Area | Endpoints |
|---|---|
| System | `GET /health`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel` |
| Projects | `POST /projects`, `GET /projects`, `GET /projects/{id}`, `DELETE /projects/{id}?confirm={id}` |
| Models | `POST /models/import` (multipart), `POST /models/reference`, `GET /models`, `GET /models/{id}`, `PUT /models/{id}/spec`, `POST /models/{id}/validate`, `GET /models/{id}/components`, `GET /models/{id}/meshes/{component}`, `POST /models/{id}/pose` |
| Features | `GET`/`POST /models/{id}/features`, `DELETE /models/{id}/features/{feature}`, `GET /models/{id}/feature-suggestions` |
| Tolerances | `GET`/`POST /tolerances?model_id=`, `PUT`/`DELETE /tolerances/{id}?model_id=` |
| Assemblies | `POST /assemblies/generate-variants`, `POST /assemblies/validate` |
| Mechanics | `POST /mechanics/configure`, `POST /tasks` (one synchronous run) |
| Experiments | `POST /experiments`, `GET /experiments`, `GET /experiments/{id}`, `POST .../run`, `GET .../progress`, `POST .../cancel`, `GET .../results`, `GET .../analysis?metric=`, `POST .../replay`, `POST .../optimise`, `GET .../analyses/{name}` |
| Calibration | `POST /measurements/import`, `GET /measurements?project_id=`, `POST /calibration`, `GET /calibration/{model_id}` |
| Reports | `GET /reports/{experiment_id}?format=json|markdown|csv|pdf` |
| Optional AI | `POST /ai/explain` |

`POST .../optimise` takes `kind`: `worst_case`, `minimise`, `allocation`, `sobol`,
`one_at_a_time` or `comparison`. Long work runs as a background job on one worker; poll
`/jobs/{id}` or the experiment's `/progress`.
