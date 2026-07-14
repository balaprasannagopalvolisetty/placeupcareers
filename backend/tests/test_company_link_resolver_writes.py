from app.etl import master_jobs
from app.workers import company_link_resolver


class _Result:
    rowcount = 1


class _Session:
    def __init__(self):
        self.master_ids = []
        self.jobs_ids = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, params=None):
        sql = str(statement).lower()
        if "update master_jobs" in sql:
            self.master_ids.append(params["id"])
        elif "update jobs" in sql:
            self.jobs_ids.append(params["id"])
        return _Result()


class _Client:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


def _rows():
    return [
        {"id": "b", "description": "", "metadata": {"checked": True}},
        {"id": "a", "description": "", "metadata": {"checked": True}},
    ]


def test_resolver_skips_master_write_when_publisher_lock_is_busy(monkeypatch):
    session = _Session()
    monkeypatch.setattr(company_link_resolver, "PostgresClient", lambda: _Client(session))
    monkeypatch.setattr(master_jobs, "try_acquire_master_jobs_lock", lambda _db: False)

    result = company_link_resolver._write_results(_rows())

    assert result == {"master_updated": 0, "jobs_updated": 2}
    assert session.master_ids == []
    assert session.jobs_ids == ["a", "b"]


def test_resolver_updates_master_in_canonical_order_when_lock_is_owned(monkeypatch):
    session = _Session()
    monkeypatch.setattr(company_link_resolver, "PostgresClient", lambda: _Client(session))
    monkeypatch.setattr(master_jobs, "try_acquire_master_jobs_lock", lambda _db: True)

    result = company_link_resolver._write_results(_rows())

    assert result == {"master_updated": 2, "jobs_updated": 2}
    assert session.master_ids == ["a", "b"]
    assert session.jobs_ids == ["a", "b"]
