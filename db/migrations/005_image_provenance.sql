-- 005_image_provenance.sql
-- Audit trail for every final image we ship to a customer.
--
-- One row per delivered image. We don't store the classifier verdict
-- here at image_proc time because the watermark classification
-- happens in an earlier stage on the operator console; that data
-- lives in data/ai_output/<batch_id>_output.json and can be attached
-- post-hoc via ``admin_cli provenance attach-verdicts``. What we
-- record at image_proc time is everything image_proc itself knows:
--
--   - the source URL of the candidate that was kept
--   - how many candidates were in the part's group (so the dedup
--     ratio is auditable)
--   - which perceptual-hash configuration matched (method, hash size,
--     threshold) — useful when explaining why two visually-different
--     images collapsed, or why two near-identical ones didn't
--   - the final S3 key + URL
--
-- The table is subject to row-level security: rows are visible only
-- when SESSION_CONTEXT('tenant_id') matches the row's tenant_id, with
-- the same parts_admin bypass as dbo.parts.
--
-- Idempotent.

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID('dbo.image_provenance', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.image_provenance (
        provenance_id      BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        tenant_id          NVARCHAR(32)   NOT NULL,
        part_number        NVARCHAR(128)  NOT NULL,
        job_id             NVARCHAR(64)   NULL,
        source_url         NVARCHAR(2048) NULL,
        candidate_count    INT            NULL,
        discarded_by_dedup INT            NULL,
        hash_method        NVARCHAR(16)   NULL,
        hash_size          INT            NULL,
        hash_threshold     INT            NULL,
        final_key          NVARCHAR(2048) NOT NULL,
        final_url          NVARCHAR(2048) NOT NULL,
        classifier_verdict NVARCHAR(MAX)  NULL,
        created_at         DATETIME2      NOT NULL CONSTRAINT DF_image_provenance_created DEFAULT (SYSUTCDATETIME())
    );

    CREATE INDEX IX_image_provenance_tenant_part
        ON dbo.image_provenance (tenant_id, part_number);

    CREATE INDEX IX_image_provenance_job
        ON dbo.image_provenance (job_id)
        WHERE job_id IS NOT NULL;
END
GO

-- Extend the existing RLS policy to cover image_provenance.
-- The migration-003 policy is dropped and recreated as a single
-- statement; CREATE SECURITY POLICY doesn't support ALTER ADD in a
-- portable way.

IF EXISTS (
    SELECT 1 FROM sys.security_policies WHERE name = 'parts_tenant_isolation'
)
BEGIN
    DROP SECURITY POLICY dbo.parts_tenant_isolation;
END
GO

CREATE SECURITY POLICY dbo.parts_tenant_isolation
    ADD FILTER PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.parts,
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.parts AFTER INSERT,
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.parts AFTER UPDATE,
    ADD FILTER PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.part_tags,
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.part_tags AFTER INSERT,
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.part_tags AFTER UPDATE,
    ADD FILTER PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.image_provenance,
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.image_provenance AFTER INSERT,
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.image_provenance AFTER UPDATE
    WITH (STATE = ON);
GO
