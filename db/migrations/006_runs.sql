-- 006_runs.sql
-- Persistent record of every operator run. The web UI uses this to
-- show "what's currently running" without depending on in-process
-- state (so a uvicorn restart doesn't lose progress visibility, and
-- a horizontally-scaled web fleet sees the same picture).
--
-- A run progresses through stages:
--
--   queued    just created; background worker hasn't picked it up
--   search    image search stage running
--   watermark AI watermark stage running
--   filter    filter / dedup stage running
--   complete  all stages done, report written
--   failed    a stage raised; ``error`` carries the message
--
-- The web UI's "/runs/{job_id}" page polls /runs/{job_id}/status
-- every 5s via HTMX to display progress.

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID('dbo.runs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.runs (
        job_id           NVARCHAR(64)  NOT NULL PRIMARY KEY,
        tenant_id        NVARCHAR(32)  NOT NULL,
        operator         NVARCHAR(128) NULL,
        stage            NVARCHAR(16)  NOT NULL CONSTRAINT DF_runs_stage DEFAULT (N'queued'),
        csv_rows         INT           NULL,
        progress_note    NVARCHAR(512) NULL,
        error            NVARCHAR(MAX) NULL,
        report_html_url  NVARCHAR(2048) NULL,
        report_json_url  NVARCHAR(2048) NULL,
        created_at       DATETIME2     NOT NULL CONSTRAINT DF_runs_created DEFAULT (SYSUTCDATETIME()),
        updated_at       DATETIME2     NOT NULL CONSTRAINT DF_runs_updated DEFAULT (SYSUTCDATETIME()),
        completed_at     DATETIME2     NULL,
        CONSTRAINT CK_runs_stage CHECK (stage IN (
            N'queued', N'search', N'watermark', N'filter',
            N'complete', N'failed'
        ))
    );

    CREATE INDEX IX_runs_tenant_created ON dbo.runs (tenant_id, created_at DESC);
    CREATE INDEX IX_runs_stage          ON dbo.runs (stage);
END
GO

-- Extend RLS to cover runs. Same SESSION_CONTEXT predicate, same
-- parts_admin bypass.

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
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.image_provenance AFTER UPDATE,
    ADD FILTER PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.runs,
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.runs AFTER INSERT,
    ADD BLOCK  PREDICATE dbo.fn_rls_tenant_predicate(tenant_id) ON dbo.runs AFTER UPDATE
    WITH (STATE = ON);
GO
