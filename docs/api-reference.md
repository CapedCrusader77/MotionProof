# API reference

Base path `/api/v1`. Interactive documentation: `/docs` on the running server. Errors are JSON
`{"error": "message"}` with status 401, 403, 404, 409, 413, 422 or 429.

Every route except `GET /health` and the `/auth/*` routes needs a session: sign in with
`POST /auth/login` (`{"email", "password"}`) and send the returned `mp_session` cookie. Each
account works in its own workspace and sees only its own jobs.

| Area | Endpoints |
|---|---|
| Accounts | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET /account` (with the number of active sessions), `POST /account/name` (`{name}`), `POST /account/sessions/end-others`, `POST /account/password` (`{current, new}`), `POST /account/delete` (`{password}`) |
| Administration (first account) | `GET /admin/users`, `POST /admin/users/{id}/password` (`{new}`), `DELETE /admin/users/{id}` |
| System | `GET /health` (public, status only), `GET /system` (versions, workspace, jobs, AI), `GET /jobs/{id}`, `POST /jobs/{id}/cancel` |
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
