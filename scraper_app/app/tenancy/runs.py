"""Persistent run state — read/write the ``dbo.runs`` table.

The Tkinter operator console kept run state on disk in
``data/state.json``; the web UI uses a SQL row instead so:

- a uvicorn restart doesn't lose progress visibility
- a horizontally-scaled web fleet shares the same picture
- the run row is RLS-isolated alongside parts / part_tags /
  provenance, so cross-tenant visibility is impossible by accident

The repository is a thin façade. The valid stage transitions and
the timestamps are enforced in code rather than in a CHECK constraint
because the rules will evolve as we add new stages (e.g. an explicit
``resubmit`` stage when we make resubmits a first-class step).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Optional

from .ids import validate_tenant_id


VALID_STAGES = ("queued", "search", "watermark", "filter", "complete", "failed")
TERMINAL_STAGES = ("complete", "failed")


@dataclasses.dataclass
class RunRecord:
    job_id: str
    tenant_id: str
    operator: Optional[str]
    stage: str
    csv_rows: Optional[int]
    progress_note: Optional[str]
    error: Optional[str]
    report_html_url: Optional[str]
    report_json_url: Optional[str]
    created_at: Optional[dt.datetime]
    updated_at: Optional[dt.datetime]
    completed_at: Optional[dt.datetime]

    @property
    def is_terminal(self) -> bool:
        return self.stage in TERMINAL_STAGES


class RunsRepository:
    """Read/write the ``dbo.runs`` table."""

    def __init__(self, db):
        self.db = db

    # ---- write -------------------------------------------------------

    def create(
        self,
        *,
        job_id: str,
        tenant_id: str,
        operator: Optional[str] = None,
        csv_rows: Optional[int] = None,
    ) -> None:
        validate_tenant_id(tenant_id)
        self.db.execute_sql(
            """
            INSERT INTO dbo.runs (job_id, tenant_id, operator, stage, csv_rows)
            VALUES (:job_id, :tenant_id, :operator, N'queued', :csv_rows);
            """,
            params={
                "job_id": job_id,
                "tenant_id": tenant_id,
                "operator": operator,
                "csv_rows": csv_rows,
            },
        )

    def set_stage(
        self,
        job_id: str,
        stage: str,
        *,
        progress_note: Optional[str] = None,
    ) -> None:
        if stage not in VALID_STAGES:
            raise ValueError(f"unknown stage {stage!r}; expected one of {VALID_STAGES}")
        completed_clause = ", completed_at = SYSUTCDATETIME()" if stage in TERMINAL_STAGES else ""
        self.db.execute_sql(
            f"""
            UPDATE dbo.runs
            SET stage = :stage,
                progress_note = :progress_note,
                updated_at = SYSUTCDATETIME(){completed_clause}
            WHERE job_id = :job_id;
            """,
            params={
                "job_id": job_id,
                "stage": stage,
                "progress_note": progress_note,
            },
        )

    def set_error(self, job_id: str, error: str) -> None:
        self.db.execute_sql(
            """
            UPDATE dbo.runs
            SET stage = N'failed',
                error = :error,
                updated_at = SYSUTCDATETIME(),
                completed_at = SYSUTCDATETIME()
            WHERE job_id = :job_id;
            """,
            params={"job_id": job_id, "error": error},
        )

    def set_report_urls(self, job_id: str, html_url: str, json_url: str) -> None:
        self.db.execute_sql(
            """
            UPDATE dbo.runs
            SET report_html_url = :html_url,
                report_json_url = :json_url,
                updated_at = SYSUTCDATETIME()
            WHERE job_id = :job_id;
            """,
            params={"job_id": job_id, "html_url": html_url, "json_url": json_url},
        )

    # ---- read --------------------------------------------------------

    def get(self, job_id: str) -> Optional[RunRecord]:
        df = self.db.read_sql_query(
            """
            SELECT job_id, tenant_id, operator, stage, csv_rows,
                   progress_note, error, report_html_url, report_json_url,
                   created_at, updated_at, completed_at
            FROM dbo.runs
            WHERE job_id = :job_id;
            """,
            params={"job_id": job_id},
        )
        if df.empty:
            return None
        return self._from_row(df.iloc[0])

    def list_recent(self, *, tenant_id: Optional[str] = None, limit: int = 50) -> list[RunRecord]:
        if tenant_id:
            df = self.db.read_sql_query(
                """
                SELECT TOP (:n) job_id, tenant_id, operator, stage, csv_rows,
                       progress_note, error, report_html_url, report_json_url,
                       created_at, updated_at, completed_at
                FROM dbo.runs
                WHERE tenant_id = :tenant_id
                ORDER BY created_at DESC;
                """,
                params={"tenant_id": tenant_id, "n": limit},
            )
        else:
            df = self.db.read_sql_query(
                """
                SELECT TOP (:n) job_id, tenant_id, operator, stage, csv_rows,
                       progress_note, error, report_html_url, report_json_url,
                       created_at, updated_at, completed_at
                FROM dbo.runs
                ORDER BY created_at DESC;
                """,
                params={"n": limit},
            )
        return [self._from_row(r) for _, r in df.iterrows()]

    @staticmethod
    def _from_row(row) -> RunRecord:
        def _opt(v):
            return v if v is not None else None

        return RunRecord(
            job_id=str(row["job_id"]),
            tenant_id=str(row["tenant_id"]),
            operator=_opt(row.get("operator")),
            stage=str(row["stage"]),
            csv_rows=int(row["csv_rows"]) if row.get("csv_rows") is not None else None,
            progress_note=_opt(row.get("progress_note")),
            error=_opt(row.get("error")),
            report_html_url=_opt(row.get("report_html_url")),
            report_json_url=_opt(row.get("report_json_url")),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            completed_at=row.get("completed_at"),
        )
