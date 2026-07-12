from app.etl.master_jobs import (
    MASTER_REBUILD_LOCK_KEY,
    MASTER_REBUILD_LOCK_SQL,
    MASTER_SYNC_SQL,
    rebuild_master_jobs,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _BusySession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return _ScalarResult(False)


def test_master_sync_has_one_shared_lock_and_deterministic_upsert_order():
    assert "pg_try_advisory_xact_lock" in MASTER_REBUILD_LOCK_SQL
    assert isinstance(MASTER_REBUILD_LOCK_KEY, int)
    assert "WHERE rn = 1\nORDER BY canonical_key\nON CONFLICT" in MASTER_SYNC_SQL


def test_busy_master_publisher_skips_without_running_the_upsert():
    session = _BusySession()

    assert rebuild_master_jobs(db=session) == 0
    assert len(session.calls) == 1
    assert "pg_try_advisory_xact_lock" in session.calls[0][0]
    assert session.calls[0][1] == {"lock_key": MASTER_REBUILD_LOCK_KEY}
