-- 007_manifest_url.sql
-- Add manifest_url to dbo.runs.
--
-- Every completed run writes three artefacts under
-- tenants/<id>/reports/<job_id>/:
--
--   index.html       — human-facing run summary (already in dbo.runs)
--   report.json      — machine-facing run summary  (already in dbo.runs)
--   manifest.csv     — customer-shareable spreadsheet: one row per
--                      delivered image with part_number, description,
--                      final_url, source_url, hash_method, etc.
--
-- The manifest is what an e-shop operator actually imports into their
-- PIM/ERP. Keeping the URL on dbo.runs lets the operator console
-- surface the link directly from the run page without re-deriving the
-- S3 key.
--
-- Idempotent.

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.runs') AND name = 'manifest_url'
)
BEGIN
    ALTER TABLE dbo.runs
        ADD manifest_url NVARCHAR(2048) NULL;
END
GO
