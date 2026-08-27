"""Durable state for the intelligence loop. SQLite, no server, no dependencies."""
from __future__ import annotations
import sqlite3, json, time, pathlib, hashlib
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
  url TEXT PRIMARY KEY, entity TEXT, tier TEXT, kind TEXT,
  sha256 TEXT, text TEXT, fetched_at REAL, changed_at REAL, status INTEGER
);
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT, kind TEXT,
  value TEXT, source_url TEXT, observed_at REAL
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, started_at REAL,
  finished_at REAL, output_tokens INTEGER, status TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE INDEX IF NOT EXISTS facts_entity ON facts(entity, kind);
"""


class Store:
    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # --- key/value -----------------------------------------------------
    def get(self, k: str, default: Any = None) -> Any:
        r = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(r["v"]) if r else default

    def set(self, k: str, v: Any) -> None:
        self.db.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                        (k, json.dumps(v)))
        self.db.commit()

    # --- documents -----------------------------------------------------
    def upsert_doc(self, url: str, entity: str, tier: str, kind: str,
                   text: str, status: int) -> bool:
        """Returns True when the content actually changed. This is the token gate:
        unchanged pages never reach a model."""
        sha = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
        now = time.time()
        row = self.db.execute("SELECT sha256 FROM docs WHERE url=?", (url,)).fetchone()
        changed = row is None or row["sha256"] != sha
        self.db.execute(
            """INSERT INTO docs(url,entity,tier,kind,sha256,text,fetched_at,changed_at,status)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(url) DO UPDATE SET
                 sha256=excluded.sha256, text=excluded.text, fetched_at=excluded.fetched_at,
                 status=excluded.status,
                 changed_at=CASE WHEN docs.sha256 != excluded.sha256
                                 THEN excluded.fetched_at ELSE docs.changed_at END""",
            (url, entity, tier, kind, sha, text, now, now, status))
        self.db.commit()
        return changed

    def doc(self, url: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM docs WHERE url=?", (url,)).fetchone()

    def changed_since(self, ts: float) -> list[sqlite3.Row]:
        """Only successfully fetched documents. A page that 403'd changed its stored
        text, but analysing an error body would spend tokens on nothing."""
        return self.db.execute(
            """SELECT * FROM docs
               WHERE changed_at > ? AND status = 200
                 AND text NOT LIKE '__FETCH_ERROR__%' AND length(text) > 200
               ORDER BY entity""", (ts,)).fetchall()

    # --- facts ---------------------------------------------------------
    def add_fact(self, entity: str, kind: str, value: str, source_url: str) -> None:
        prev = self.db.execute(
            "SELECT value FROM facts WHERE entity=? AND kind=? ORDER BY observed_at DESC LIMIT 1",
            (entity, kind)).fetchone()
        if prev and prev["value"] == value:
            return                      # no churn, no row
        self.db.execute(
            "INSERT INTO facts(entity,kind,value,source_url,observed_at) VALUES(?,?,?,?,?)",
            (entity, kind, value, source_url, time.time()))
        self.db.commit()

    def latest_facts(self, entity: str | None = None) -> list[sqlite3.Row]:
        q = """SELECT entity,kind,value,source_url,MAX(observed_at) AS observed_at
               FROM facts {} GROUP BY entity,kind ORDER BY entity,kind"""
        if entity:
            return self.db.execute(q.format("WHERE entity=?"), (entity,)).fetchall()
        return self.db.execute(q.format(""), ()).fetchall()

    # --- runs / budget -------------------------------------------------
    def start_run(self, kind: str) -> int:
        cur = self.db.execute("INSERT INTO runs(kind,started_at,status) VALUES(?,?,'running')",
                              (kind, time.time()))
        self.db.commit()
        return int(cur.lastrowid)

    def finish_run(self, rid: int, tokens: int, status: str, note: str = "") -> None:
        self.db.execute(
            "UPDATE runs SET finished_at=?, output_tokens=?, status=?, note=? WHERE id=?",
            (time.time(), tokens, status, note[:2000], rid))
        self.db.commit()

    def tokens_last_24h(self) -> int:
        r = self.db.execute(
            "SELECT COALESCE(SUM(output_tokens),0) AS t FROM runs WHERE started_at > ?",
            (time.time() - 86400,)).fetchone()
        return int(r["t"])
