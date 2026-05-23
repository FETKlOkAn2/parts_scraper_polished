# Operator web console

FastAPI + Jinja2 + HTMX. Replaces the Tkinter GUI as the day-to-day
operator surface. Both UIs call into the same `Helper` / `Database` /
`BatchWatermarkDetector` underneath, so adopting the web console is a
deployment swap, not a rewrite.

## Running

```bash
export AUTH_USERNAME=operator
export AUTH_PASSWORD='<long random>'
export SECRET_KEY='<another long random>'  # signs the session cookie
export BUCKET=acme-parts-pipeline
export DB_HOST=...
export DB_PORT=1433
export DB_USER=parts_app
export DB_PASSWORD=...
export OPENAI_API_KEY=sk-...
export DEFAULT_TENANT_ID=acme-parts            # optional fallback
export SEARCH_QUEUE_URL=...                    # same as Tkinter GUI
export PROC_QUEUE_URL=...
export SEARCH_KEY=search_jobs
export PROC_KEY=proc_jobs

cd gui_app/app
uvicorn web.main:app --host 0.0.0.0 --port 8000
```

In production, put it behind nginx (or directly behind an ALB) with
TLS terminated upstream. The app refuses to start if `AUTH_USERNAME`
/ `AUTH_PASSWORD` / `SECRET_KEY` are unset — a publicly-reachable
operator console with no auth is the single failure mode we never
want.

## Surfaces

| Path | What |
| --- | --- |
| `GET /` | Tenant picker + the run-start form. |
| `POST /tenant` | Set the active tenant on this session. |
| `POST /tenant/clear` | Clear it. |
| `GET /tenants` | List, edit, change status / quota. |
| `POST /tenants` | Upsert a tenant. |
| `POST /run/start` | Upload CSV + kick off image-search stage. |
| `POST /runs/{job_id}/watermark` | Run the AI watermark stage. |
| `POST /runs/{job_id}/filter` | Run the dedup / final-image stage. |
| `POST /runs/{job_id}/resubmit-failed` | Resubmit just the OpenAI batches that came back unusable. |
| `GET /runs` | Recent runs (RLS-scoped). |
| `GET /runs/{job_id}` | Full status page with live HTMX polling. |
| `GET /runs/{job_id}/status` | The status partial (HTMX endpoint). |
| `GET /reports` | Recent runs with a published report URL. |
| `GET /provenance` | Audit trail search by part number or job id. |
| `GET /healthz` | Liveness probe; bypasses auth so an ALB can hit it. |
| `GET /readyz` | Deeper readiness; auth-gated. |
| `GET /api/docs` | OpenAPI schema. Not linked from the UI. |

## How stages run

Each POST endpoint that "kicks off a stage" creates or updates the
`dbo.runs` row, schedules a synchronous stage body via
`asyncio.to_thread`, and immediately redirects to `/runs/{job_id}`.
The status page polls the partial endpoint every 5 seconds via HTMX
until the run hits a terminal state (`complete` or `failed`), at
which point the server response includes `HX-Trigger: run-terminal`
and polling stops.

On process restart, the `lifespan` startup hook calls
`adopt_orphaned_runs()` which marks every non-terminal run as
`failed` with a "uvicorn restart" marker. The underlying AWS work
might still be ongoing but we can't track it; the operator restarts
from a clean state.

## HTMX

We load HTMX 1.9.12 from `unpkg` with SRI. For air-gapped operator
workstations, vendor the file into `static/htmx.min.js` and update
`templates/base.html` to point at it.

## Tests

Integration tests in `tests/test_web_*.py` use FastAPI's `TestClient`
with the `db` dependency overridden to a MagicMock. No real SQL
Server / S3 needed. 214 tests total across the project (~50 are web).
