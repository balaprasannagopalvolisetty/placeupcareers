"""Transfer core jobs tables from Cloud SQL to Supabase.

This is intentionally a one-way, streaming copy for the hybrid migration:
Cloud SQL (via local cloud-sql-proxy on 127.0.0.1:5433) -> Supabase Postgres.

Required:
  - cloud-sql-proxy running locally for steel-shine-492401-u6:us-east1:placeup-backend
  - source DATABASE_URL available in GCP Secret Manager
  - target Supabase URL in SUPABASE_DB_URL or GCP secret DATABASE_URL_SUPABASE

The script recreates only the four jobs-domain tables requested by the
migration: companies, jobs, silver_posts, master_jobs.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass
from typing import Iterable

import psycopg
from psycopg import sql


PROJECT_ID = "steel-shine-492401-u6"
SOURCE_SECRET = "DATABASE_URL"
TARGET_SECRET = "DATABASE_URL_SUPABASE"
TABLES = ("companies", "jobs", "silver_posts", "master_jobs")


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    not_null: bool
    default_expr: str | None
    identity: str
    generated: str


def _secret(name: str) -> str:
    return subprocess.check_output(
        [
            "gcloud.cmd",
            "secrets",
            "versions",
            "access",
            "latest",
            "--secret",
            name,
            "--project",
            PROJECT_ID,
        ],
        text=True,
    ).strip()


def _normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def source_conninfo() -> str:
    raw = _normalize_url(_secret(SOURCE_SECRET))
    parsed = urllib.parse.urlparse(raw)
    password = urllib.parse.unquote(parsed.password or "")
    return (
        f"postgresql://{parsed.username}:{urllib.parse.quote(password, safe='')}"
        f"@127.0.0.1:5433/{parsed.path.lstrip('/')}"
    )


def target_conninfo() -> str:
    url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not url:
        try:
            url = _secret(TARGET_SECRET)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Set SUPABASE_DB_URL or create GCP secret DATABASE_URL_SUPABASE."
            ) from exc
    return _normalize_url(url)


def qname(table: str) -> sql.Composed:
    return sql.SQL("public.{}").format(sql.Identifier(table))


def fetch_columns(conn: psycopg.Connection, table: str) -> list[Column]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select a.attname,
                   format_type(a.atttypid, a.atttypmod),
                   a.attnotnull,
                   pg_get_expr(d.adbin, d.adrelid) as default_expr,
                   a.attidentity,
                   a.attgenerated
            from pg_attribute a
            join pg_class c on c.oid = a.attrelid
            join pg_namespace n on n.oid = c.relnamespace
            left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
            where n.nspname = 'public'
              and c.relname = %s
              and a.attnum > 0
              and not a.attisdropped
            order by a.attnum
            """,
            (table,),
        )
        return [
            Column(
                name=row[0],
                data_type=row[1],
                not_null=bool(row[2]),
                default_expr=row[3],
                identity=row[4] or "",
                generated=row[5] or "",
            )
            for row in cur.fetchall()
        ]


def fetch_constraints(conn: psycopg.Connection, table: str) -> list[tuple[str, str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select conname, contype, pg_get_constraintdef(oid)
            from pg_constraint
            where conrelid = (%s)::regclass
              and contype in ('p', 'u', 'f', 'c')
            order by case contype when 'p' then 1 when 'u' then 2
                                    when 'c' then 3 when 'f' then 4 else 5 end,
                     conname
            """,
            (f"public.{table}",),
        )
        return [(row[0], row[1], row[2]) for row in cur.fetchall()]


def fetch_indexes(conn: psycopg.Connection, table: str) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select i.indexname, i.indexdef
            from pg_indexes i
            left join pg_constraint c
              on c.conname = i.indexname and c.conrelid = (%s)::regclass
            where i.schemaname = 'public'
              and i.tablename = %s
              and c.oid is null
            order by i.indexname
            """,
            (f"public.{table}", table),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]


def create_tables(src: psycopg.Connection, dst: psycopg.Connection, *, drop: bool) -> None:
    with dst.cursor() as cur:
        cur.execute("create extension if not exists pgcrypto")
        cur.execute("create extension if not exists pg_trgm")
        if drop:
            joined = sql.SQL(", ").join(qname(t) for t in reversed(TABLES))
            cur.execute(sql.SQL("drop table if exists {} cascade").format(joined))

    for table in TABLES:
        columns = fetch_columns(src, table)
        if not columns:
            raise RuntimeError(f"Source table public.{table} was not found.")
        col_defs = []
        for col in columns:
            parts = [
                sql.Identifier(col.name),
                sql.SQL(col.data_type),
            ]
            if col.default_expr:
                parts.extend([sql.SQL("default"), sql.SQL(col.default_expr)])
            if col.not_null:
                parts.append(sql.SQL("not null"))
            col_defs.append(sql.SQL(" ").join(parts))
        ddl = sql.SQL("create table if not exists {} ({})").format(
            qname(table),
            sql.SQL(", ").join(col_defs),
        )
        with dst.cursor() as cur:
            print(f"Creating public.{table} ...", flush=True)
            cur.execute(ddl)
    dst.commit()


def copy_table(src: psycopg.Connection, dst: psycopg.Connection, table: str) -> int:
    columns = fetch_columns(src, table)
    col_list = sql.SQL(", ").join(sql.Identifier(c.name) for c in columns)
    copy_out = sql.SQL("copy {} ({}) to stdout with (format csv)").format(qname(table), col_list)
    copy_in = sql.SQL("copy {} ({}) from stdin with (format csv)").format(qname(table), col_list)
    with src.cursor() as scur:
        scur.execute(sql.SQL("select count(*) from {}").format(qname(table)))
        expected = int(scur.fetchone()[0])

    print(f"Copying public.{table}: {expected:,} rows ...", flush=True)
    start = time.monotonic()
    bytes_written = 0
    with src.cursor().copy(copy_out) as source_copy:
        with dst.cursor().copy(copy_in) as target_copy:
            for chunk in source_copy:
                bytes_written += len(chunk)
                target_copy.write(chunk)
    dst.commit()
    elapsed = max(0.1, time.monotonic() - start)
    print(
        f"Copied public.{table}: {expected:,} rows, "
        f"{bytes_written / (1024 * 1024):,.1f} MiB CSV in {elapsed / 60:,.1f} min",
        flush=True,
    )
    return expected


def add_constraints_and_indexes(src: psycopg.Connection, dst: psycopg.Connection) -> None:
    for table in TABLES:
        for name, _typ, definition in fetch_constraints(src, table):
            with dst.cursor() as cur:
                print(f"Adding constraint {name} on public.{table} ...", flush=True)
                cur.execute(
                    sql.SQL("alter table {} add constraint {} {}").format(
                        qname(table),
                        sql.Identifier(name),
                        sql.SQL(definition),
                    )
                )
            dst.commit()
        for name, indexdef in fetch_indexes(src, table):
            print(f"Creating index {name} ...", flush=True)
            with dst.cursor() as cur:
                cur.execute(sql.SQL(indexdef))
            dst.commit()


def verify_counts(src: psycopg.Connection, dst: psycopg.Connection, tables: Iterable[str]) -> bool:
    ok = True
    for table in tables:
        with src.cursor() as scur, dst.cursor() as dcur:
            scur.execute(sql.SQL("select count(*) from {}").format(qname(table)))
            dcur.execute(sql.SQL("select count(*) from {}").format(qname(table)))
            source_count = int(scur.fetchone()[0])
            target_count = int(dcur.fetchone()[0])
        status = "OK" if source_count == target_count else "MISMATCH"
        print(f"{table}: source={source_count:,} supabase={target_count:,} {status}")
        ok = ok and source_count == target_count
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-drop", action="store_true", help="Do not drop/recreate target tables first.")
    parser.add_argument("--schema-only", action="store_true", help="Create target tables only.")
    parser.add_argument("--verify-only", action="store_true", help="Only compare row counts.")
    args = parser.parse_args()

    with psycopg.connect(source_conninfo()) as src, psycopg.connect(target_conninfo(), connect_timeout=30) as dst:
        if args.verify_only:
            return 0 if verify_counts(src, dst, TABLES) else 1
        create_tables(src, dst, drop=not args.no_drop)
        if args.schema_only:
            return 0
        for table in TABLES:
            copy_table(src, dst, table)
        add_constraints_and_indexes(src, dst)
        return 0 if verify_counts(src, dst, TABLES) else 1


if __name__ == "__main__":
    sys.exit(main())
