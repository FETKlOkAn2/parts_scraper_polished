"""Provenance writing + the matched-config return shape from try_mulitiple_hashes."""
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from image_proc.image_processing import Img_Proc


@pytest.fixture
def proc():
    return Img_Proc.__new__(Img_Proc)


# ---- try_mulitiple_hashes returns (keep, matched_config) ---------------

class _StubProc(Img_Proc):
    """Subclass that lets us control which hash config 'matches'."""

    def __init__(self, matching_cfg):
        self._match = matching_cfg

    def hash_and_compare_group(self, files, method, hash_size, distance_thresh, testing):
        if (
            self._match
            and method == self._match["method"]
            and hash_size == self._match["hash_size"]
            and distance_thresh == self._match["threshold"]
        ):
            return list(files)
        return []


def test_try_multiple_hashes_returns_matched_config():
    proc = _StubProc({"method": "ahash", "hash_size": 16, "threshold": 18})
    keep, cfg = proc.try_mulitiple_hashes(["a.png", "b.png", "c.png"])
    assert keep == ["a.png", "b.png", "c.png"]
    assert cfg == {"method": "ahash", "hash_size": 16, "threshold": 18}


def test_try_multiple_hashes_returns_none_config_on_no_match():
    proc = _StubProc(None)  # nothing matches
    keep, cfg = proc.try_mulitiple_hashes(["a.png", "b.png"])
    assert keep == ["a.png"]   # falls back to first candidate
    assert cfg is None


def test_try_multiple_hashes_picks_first_winning_config_in_priority_order():
    """phash@10 should win over ahash@12 even when both 'match'."""
    class _MultiMatchProc(Img_Proc):
        def hash_and_compare_group(self, files, method, hash_size, distance_thresh, testing):
            # Always returns a hit, regardless of config.
            return list(files)

    proc = _MultiMatchProc.__new__(_MultiMatchProc)
    keep, cfg = proc.try_mulitiple_hashes(["a.png"])
    # First in the configs list is phash @ threshold 10.
    assert cfg == {"method": "phash", "hash_size": 8, "threshold": 10}


# ---- Database.record_provenance ----------------------------------------

def test_record_provenance_inserts_with_tenant_id():
    from image_proc.database import Database
    db = Database.__new__(Database)
    db.tenant_id = "acme"
    db.execute_sql = MagicMock()

    ok = db.record_provenance(
        part_number="AB123",
        source_url="tenants/acme/images/AB123_disc_0.png",
        candidate_count=8,
        discarded_by_dedup=7,
        hash_method="phash",
        hash_size=8,
        hash_threshold=14,
        final_key="tenants/acme/final/xyz.png",
        final_url="https://acme-bucket/tenants/acme/final/xyz.png",
        job_id="20260523T120000-deadbeef",
    )

    assert ok is True
    sql = db.execute_sql.call_args.args[0]
    assert "INSERT INTO dbo.image_provenance" in sql
    params = db.execute_sql.call_args.kwargs["params"]
    assert params["tenant_id"] == "acme"
    assert params["part_number"] == "AB123"
    assert params["candidate_count"] == 8
    assert params["discarded_by_dedup"] == 7
    assert params["hash_method"] == "phash"
    assert params["hash_threshold"] == 14
    assert params["job_id"] == "20260523T120000-deadbeef"


def test_record_provenance_swallows_db_errors():
    """The customer's image is already in S3 + the parts row is updated.
    An audit-trail failure must not undo that."""
    from image_proc.database import Database
    db = Database.__new__(Database)
    db.tenant_id = "acme"
    db.execute_sql = MagicMock(side_effect=RuntimeError("table doesn't exist"))

    ok = db.record_provenance(
        part_number="AB123",
        source_url="s",
        candidate_count=1,
        discarded_by_dedup=0,
        hash_method=None,
        hash_size=None,
        hash_threshold=None,
        final_key="k",
        final_url="u",
    )
    assert ok is False  # signalled, but no exception


def test_record_provenance_accepts_none_for_optional_hash_fields():
    """When try_mulitiple_hashes falls back (no method matched), the
    config dict is None and we still need a row written."""
    from image_proc.database import Database
    db = Database.__new__(Database)
    db.tenant_id = "acme"
    db.execute_sql = MagicMock()

    ok = db.record_provenance(
        part_number="AB123",
        source_url="s",
        candidate_count=3,
        discarded_by_dedup=2,
        hash_method=None,
        hash_size=None,
        hash_threshold=None,
        final_key="k",
        final_url="u",
    )
    assert ok is True
    params = db.execute_sql.call_args.kwargs["params"]
    assert params["hash_method"] is None
    assert params["hash_size"] is None
    assert params["hash_threshold"] is None
