from sqlalchemy.exc import OperationalError

from app.etl import master_jobs as master_jobs_module
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


class _RowcountResult:
    rowcount = 17


class _NestedTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _DeadlockError(Exception):
    sqlstate = "40P01"


class _BusySession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return _ScalarResult(False)


class _DeadlockThenSuccessSession:
    def __init__(self):
        self.sync_attempts = 0
        self.savepoints = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        if "pg_try_advisory_xact_lock" in sql:
            return _ScalarResult(True)
        self.sync_attempts += 1
        if self.sync_attempts == 1:
            raise OperationalError(sql, params or {}, _DeadlockError("deadlock"))
        return _RowcountResult()

    def begin_nested(self):
        self.savepoints += 1
        return _NestedTransaction()


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


def test_deadlock_retries_inside_savepoint_without_losing_outer_transaction(monkeypatch):
    session = _DeadlockThenSuccessSession()
    sleeps = []
    monkeypatch.setattr(master_jobs_module.time, "sleep", sleeps.append)

    assert rebuild_master_jobs(db=session) == 17
    assert session.sync_attempts == 2
    assert session.savepoints == 2
    assert sleeps == [0.25]
