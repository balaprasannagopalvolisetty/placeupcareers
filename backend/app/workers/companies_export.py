"""
Daily export of the deduplicated company + location list from `master_jobs`.

What it does
------------
1. Queries master_jobs for every DISTINCT (company, location) pair.
2. Renders the result as a CSV attachment + an HTML body table.
3. Emails it to operations@placeupcareer.com (or whoever you configure).
4. Optionally appends/overwrites rows in a Google Sheet so the ops team
   can pivot on it without opening their inbox.

The script is idempotent — running it twice in a row produces the same
output. It's designed to run as a Cloud Run Job triggered by Cloud
Scheduler (recommended: daily at 06:00 UTC, i.e. cron `0 6 * * *`).

Configuration
-------------
Required to send email:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD   (already wired in settings)
    COMPANIES_EXPORT_TO   (defaults to operations@placeupcareer.com)
    COMPANIES_EXPORT_FROM (defaults to SMTP_USER)

Optional — turns on Google Sheets sync when ALL three are set:
    COMPANIES_EXPORT_SHEET_ID   — Sheet ID from the URL (the long string).
    COMPANIES_EXPORT_SHEET_TAB  — Tab name to write into, default "companies".
    COMPANIES_EXPORT_CREATE_SHEET — when true and no sheet ID is set, create
                                      a new spreadsheet and log its ID.
    COMPANIES_EXPORT_SHARE_EMAIL  — email to share newly created sheets with,
                                      default operations@placeupcareer.com.
    GOOGLE_APPLICATION_CREDENTIALS  — path to a service-account JSON with
                                      "Sheets API: edit" on that sheet.

Run locally:
    python -m app.workers.companies_export

Cloud Run Job command (see deploy_separate_cloud_run.ps1):
    --command python --args "-m,app.workers.companies_export"
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Iterable, List, Tuple

from sqlalchemy import text

from app.config import settings
from app.db.postgres import PostgresClient

logger = logging.getLogger("placeup.workers.companies_export")


DEFAULT_RECIPIENT = "operations@placeupcareer.com"
DEFAULT_SHEET_TAB = "companies"
DEFAULT_SHEET_TITLE = "PlaceUp Master Company Locations"

# Query the merged source of truth and collapse every duplicate
# (company, location) pair. This intentionally does not filter to
# status='active' because operations asked for the master database list,
# not just currently visible frontend jobs.
DISTINCT_COMPANIES_SQL = """
SELECT
    company,
    coalesce(location, '') AS location
FROM master_jobs
WHERE coalesce(company, '') <> ''
GROUP BY company, coalesce(location, '')
ORDER BY company ASC, location ASC
"""


def fetch_unique_companies(client: PostgresClient | None = None) -> List[Tuple[str, str]]:
    """Run the dedupe query and return rows.

    Returned tuple shape: (company, location).
    """
    client = client or PostgresClient()
    with client.session() as db:
        rows = db.execute(text(DISTINCT_COMPANIES_SQL)).all()
    logger.info("Fetched %s unique (company, location) pairs from master_jobs.", len(rows))
    return [tuple(r) for r in rows]


# ─── CSV / email rendering ────────────────────────────────────────────

def render_csv(rows: Iterable[Tuple]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["company", "location"])
    for company, location in rows:
        writer.writerow([company or "", location or ""])
    return buf.getvalue()


def render_html_body(rows: List[Tuple], generated_at: datetime) -> str:
    total_pairs = len(rows)
    total_companies = len({r[0] for r in rows})
    total_locations = len({r[1] for r in rows if r[1]})
    # Keep the email useful without making it huge; the full list is in
    # the CSV attachment and/or the configured Google Sheet.
    preview_rows = rows[:25]
    table_rows = "\n".join(
        f"<tr><td>{_html_escape(c)}</td><td>{_html_escape(l)}</td></tr>"
        for c, l in preview_rows
    )
    return f"""\
<!doctype html>
<html>
<body style="font-family: -apple-system, Segoe UI, sans-serif; color: #222;">
  <h2 style="margin-bottom:4px">PlaceUp company list export</h2>
  <p style="color:#666; margin-top:0">
    Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')} from <code>master_jobs</code>.
  </p>
  <table style="border-collapse:collapse; margin:18px 0;">
    <tr><td><b>Unique companies</b></td><td>{total_companies:,}</td></tr>
    <tr><td><b>Unique (company, location) pairs</b></td><td>{total_pairs:,}</td></tr>
    <tr><td><b>Distinct locations</b></td><td>{total_locations:,}</td></tr>
  </table>
  <p>Full deduped list attached as <b>companies.csv</b>. First 25 rows:</p>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; font-size:13px;">
    <tr style="background:#f4f4f4">
      <th align="left">Company</th><th align="left">Location</th>
    </tr>
    {table_rows}
  </table>
  <p style="color:#888; font-size:12px; margin-top:24px">
    Source query: <code>SELECT DISTINCT company, location FROM master_jobs</code>.
    Runs via Cloud Run Job <code>placeup-companies-export</code>.
  </p>
</body>
</html>
"""


def _html_escape(text_value: str | None) -> str:
    if text_value is None:
        return ""
    return (
        str(text_value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ─── Delivery: email ──────────────────────────────────────────────────

def send_email(*, csv_text: str, html_body: str, generated_at: datetime, dry_run: bool) -> bool:
    """Email the export. Returns True if the message was actually sent."""
    recipient = os.getenv("COMPANIES_EXPORT_TO", DEFAULT_RECIPIENT)
    sender = os.getenv("COMPANIES_EXPORT_FROM") or getattr(settings, "smtp_user", None)
    subject = f"PlaceUp company list — {generated_at.strftime('%Y-%m-%d')}"

    if dry_run:
        logger.info("DRY RUN — would email %s (%s bytes CSV).", recipient, len(csv_text))
        return False

    smtp_host = getattr(settings, "smtp_host", None)
    smtp_port = getattr(settings, "smtp_port", None)
    smtp_user = getattr(settings, "smtp_user", None)
    smtp_password = getattr(settings, "smtp_password", None)
    if not (smtp_host and smtp_port and smtp_user and smtp_password):
        logger.warning(
            "SMTP not configured (SMTP_HOST/PORT/USER/PASSWORD missing). "
            "Skipping email — set them in Cloud Run env to enable delivery."
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender or smtp_user
    msg["To"] = recipient
    msg.set_content(
        "The PlaceUp company export is attached. See companies.csv for the "
        "deduplicated (company, location) list pulled from master_jobs."
    )
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(
        csv_text.encode("utf-8"),
        maintype="text",
        subtype="csv",
        filename=f"companies_{generated_at.strftime('%Y%m%d')}.csv",
    )

    # Most providers (Gmail, SES, Postmark, SendGrid SMTP) require STARTTLS
    # on port 587 or implicit TLS on 465. Detect both.
    use_implicit_tls = int(smtp_port) == 465
    try:
        if use_implicit_tls:
            with smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=30) as smtp:
                smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, int(smtp_port), timeout=30) as smtp:
                smtp.starttls()
                smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
    except Exception as exc:
        # Don't crash the Cloud Run Job — Sheets sync may still succeed.
        logger.exception("Email send failed: %s", exc)
        return False
    logger.info("Email sent to %s (%s rows, %s bytes CSV).", recipient, csv_text.count("\n") - 1, len(csv_text))
    return True


# ─── Delivery: Google Sheets (optional) ──────────────────────────────

def write_to_google_sheet(rows: List[Tuple], *, dry_run: bool) -> bool:
    """Replace the contents of the configured tab with the export.

    No-op when COMPANIES_EXPORT_SHEET_ID is not set unless
    COMPANIES_EXPORT_CREATE_SHEET=true. When the job creates a sheet, it
    logs the Sheet ID so we can store that ID in Secret Manager and keep
    all future runs updating the same master sheet.
    """
    sheet_id = os.getenv("COMPANIES_EXPORT_SHEET_ID", "").strip()
    create_sheet = os.getenv("COMPANIES_EXPORT_CREATE_SHEET", "").strip().lower() in {"1", "true", "yes", "on"}
    tab = os.getenv("COMPANIES_EXPORT_SHEET_TAB", DEFAULT_SHEET_TAB)

    if not sheet_id and not create_sheet:
        logger.info("COMPANIES_EXPORT_SHEET_ID not set; skipping Google Sheets sync.")
        return False

    if dry_run:
        target = sheet_id or f"new spreadsheet tab {tab}"
        logger.info("DRY RUN — would write %s rows to %s.", len(rows), target)
        return False

    try:
        # Lazy import so the worker still runs (email-only) without these
        # packages installed. Add `google-api-python-client` and
        # `google-auth` to requirements.txt to enable.
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
    except ImportError:
        logger.warning(
            "google-api-python-client / google-auth not installed; "
            "Sheets sync skipped. Run "
            "`pip install google-api-python-client google-auth` to enable."
        )
        return False

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    # GOOGLE_APPLICATION_CREDENTIALS is the standard Google ADC env var.
    # Cloud Run mounts service-account credentials at this path
    # automatically when you bind a SA to the job — no extra config.
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and os.path.exists(creds_path):
        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
    else:
        # Application Default Credentials — works on Cloud Run with a
        # bound service account, no key file needed.
        import google.auth  # type: ignore
        creds, _ = google.auth.default(scopes=scopes)

    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    sheets = service.spreadsheets()

    if not sheet_id:
        title = os.getenv("COMPANIES_EXPORT_SHEET_TITLE", DEFAULT_SHEET_TITLE)
        try:
            created = sheets.create(
                body={
                    "properties": {"title": title},
                    "sheets": [{"properties": {"title": tab}}],
                },
                fields="spreadsheetId,spreadsheetUrl",
            ).execute()
        except Exception as exc:
            logger.exception(
                "Google Sheet creation failed. Create a sheet manually or run gcloud auth login "
                "with Sheets/Drive scopes, then store COMPANIES_EXPORT_SHEET_ID: %s",
                exc,
            )
            return False
        sheet_id = created["spreadsheetId"]
        logger.info(
            "Created Google Sheet for companies export: id=%s url=%s",
            sheet_id,
            created.get("spreadsheetUrl"),
        )

        share_email = os.getenv("COMPANIES_EXPORT_SHARE_EMAIL", DEFAULT_RECIPIENT).strip()
        if share_email:
            try:
                drive = build("drive", "v3", credentials=creds, cache_discovery=False)
                drive.permissions().create(
                    fileId=sheet_id,
                    sendNotificationEmail=False,
                    body={"type": "user", "role": "writer", "emailAddress": share_email},
                    fields="id",
                ).execute()
                logger.info("Shared companies export sheet %s with %s.", sheet_id, share_email)
            except Exception as exc:
                logger.exception("Created sheet %s, but sharing with %s failed: %s", sheet_id, share_email, exc)

    header = ["company", "location"]
    values = [header]
    for company, location in rows:
        values.append([company or "", location or ""])

    # Wipe the tab first so removed companies actually disappear; then
    # bulk-write the fresh export. This is the only way to express
    # "the sheet should EXACTLY mirror the query" without leaving stale
    # rows from previous runs hanging around at the bottom.
    sheets.values().clear(spreadsheetId=sheet_id, range=tab).execute()
    sheets.values().update(
        spreadsheetId=sheet_id,
        range=f"{tab}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    logger.info("Wrote %s rows to sheet %s tab %s.", len(values) - 1, sheet_id, tab)
    return True


# ─── Entry point ──────────────────────────────────────────────────────

def run(dry_run: bool = False) -> dict:
    started = time.monotonic()
    generated_at = datetime.now(tz=timezone.utc)

    rows = fetch_unique_companies()
    csv_text = render_csv(rows)
    html_body = render_html_body(rows, generated_at)

    email_sent = send_email(csv_text=csv_text, html_body=html_body, generated_at=generated_at, dry_run=dry_run)
    sheet_written = write_to_google_sheet(rows, dry_run=dry_run)

    summary = {
        "rows": len(rows),
        "unique_companies": len({r[0] for r in rows}),
        "email_sent": email_sent,
        "sheet_written": sheet_written,
        "duration_seconds": round(time.monotonic() - started, 2),
        "generated_at": generated_at.isoformat(),
    }
    logger.info("companies_export complete: %s", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Email + Sheets export of unique companies from master_jobs.")
    parser.add_argument("--dry-run", action="store_true", help="Compute the export but don't send email or write to Sheets.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    summary = run(dry_run=args.dry_run)
    import json
    print(json.dumps(summary, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
