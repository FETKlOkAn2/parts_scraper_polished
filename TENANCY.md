# Multi-tenancy

This document describes how a single deployment of the parts pipeline
serves multiple end customers (tenants) from the same workers, S3
bucket, SQL database, and CloudWatch namespace.

The rollout is staged across four phases. Phase 1 is in place; the
later phases land in their own commits.

| Phase | What | Status |
| --- | --- | --- |
| 1 | Foundation: `tenancy/` package (ids, paths, envelope), SQL migration, tests, docs. No production code path moves yet. | done |
| 2 | Workers read `tenant_id` from the SQS envelope, use `TenantPaths` for every S3 key, query SQL with `tenant_id` in the predicate. | pending |
| 3 | Operator GUI picks a tenant per run; helpers stamp `tenant_id` on every SQS message; the run report lives under the tenant prefix; OpenAI batches carry the tenant id in metadata. | pending |
| 4 | Terraform: per-tenant Secrets Manager entries (so a leaked HMAC key is bounded to one tenant); per-tenant CloudWatch dashboards / alarms; an "onboard a tenant" workflow. | pending |

## Tenant identifier

A tenant id is a lowercase string, 2–32 characters, starting with a
letter, made of `[a-z0-9-]` with no leading or trailing hyphen. The
shape matches the existing Terraform `customer` variable so they can
be set to the same value when a deployment is single-tenant.

The allow-list is enforced at the boundary (`tenancy.validate_tenant_id`),
which means downstream callers can interpolate the value into S3 keys,
CloudWatch dimensions, and SQL `tenant_id` parameters without worrying
about escaping.

## S3 path scheme

Every key in the pipeline bucket now sits under `tenants/<tenant_id>/`:

```
tenants/<tenant_id>/search_jobs/chunk_N.csv
tenants/<tenant_id>/search_jobs/chunk_N.csv.done
tenants/<tenant_id>/proc_jobs/chunk_N.csv
tenants/<tenant_id>/images/<part>_<n>.png
tenants/<tenant_id>/final/<hmac-digest>.png
tenants/<tenant_id>/reports/<job_id>/index.html
```

Callers go through `tenancy.TenantPaths` rather than building these
strings by hand. The helper also has a `normalise()` method that
promotes a legacy un-scoped key (`search_jobs/foo.csv`) to its
tenant-scoped form, which is what phase-2 workers use when they
process an old in-flight message during the cutover.

## SQL schema

Both `dbo.parts` and `dbo.part_tags` gain a `tenant_id NVARCHAR(32)
NOT NULL` column. The previous unique constraint on
`dbo.parts.number` becomes `(tenant_id, number)`, so two different
tenants can legitimately use the same part number.

A trigger on `dbo.part_tags` rejects inserts/updates where
`part_tags.tenant_id` doesn't match the parent `parts.tenant_id`.
This is a defence-in-depth against an application bug that forgets the
tenant predicate.

See [`db/migrations/`](db/migrations) for the idempotent SQL.

## SQS message envelope

Operator-side code never builds raw JSON bodies — it goes through
`tenancy.envelope()`:

```json
{
  "v": 1,
  "tenant_id": "acme-parts",
  "s3_key": "tenants/acme-parts/search_jobs/chunk_3.csv",
  "job_id": "20260522T143107-deadbeef",
  "submitted_at": "2026-05-22T14:31:07Z"
}
```

- `v` lets us evolve the wire format later. Workers refuse a body with
  `v` higher than they know.
- `tenant_id` is required for new messages. A legacy body without it
  is accepted and the worker falls back to `$DEFAULT_TENANT_ID`.
- `submitted_at` is informational; useful when reading DLQs months
  later.

## Backward compatibility

Existing single-tenant deployments keep working without code changes
on day one of the rollout:

1. Apply migration `002_tenant_id.sql` with `LEGACY_TENANT=<id>`. All
   existing rows are stamped with that id.
2. Export `DEFAULT_TENANT_ID=<id>` on every worker and on the operator
   console. The phase-2 worker code uses this as the fallback when an
   in-flight SQS message lacks the new `tenant_id` field.
3. The old un-scoped S3 keys keep working until the operator runs a
   one-shot copy job that rewrites `search_jobs/...` →
   `tenants/<id>/search_jobs/...`. Until that's done, the workers
   call `TenantPaths.normalise()` on incoming keys.

Once the cutover is complete, the legacy `DEFAULT_TENANT_ID`
mechanism can stay in place indefinitely; it just becomes
"single-tenant deployments get to skip the tenant picker".

## Isolation guarantees today

In phase 1 these are the isolation properties **after** workers and
operator catch up in phases 2 and 3:

- **S3:** each tenant's keys live under a distinct prefix. IAM can
  scope a worker's `s3:GetObject`/`PutObject` to one tenant using a
  resource pattern like `arn:aws:s3:::<bucket>/tenants/<id>/*`.
  Today the worker policy is broader (the whole bucket) because all
  tenants run on the same fleet; tightening it is a phase-4 option.
- **SQL:** every read and write filters by `tenant_id`. A bug that
  forgets the predicate on `part_tags` is caught by the trigger.
  Cross-tenant reads on `parts` are not enforced at the database
  layer; that's an application invariant.
- **Secrets:** phase 1 still uses a single shared `HTML_SECRET`. Phase
  4 introduces per-tenant secrets so a leak is bounded.
- **CloudWatch:** every custom metric already carries a `Customer`
  dimension. After phase 3 that dimension takes the tenant id, so the
  dashboard slices cleanly per tenant.

## What you don't get yet

This isn't a SaaS control plane. There is no admin UI, no per-tenant
billing meter, no quota or rate limiting. The expectation is that the
operator (you, or the agency reseller) maintains a short tenant list
out of band and feeds tenant ids into the GUI at run-start.
