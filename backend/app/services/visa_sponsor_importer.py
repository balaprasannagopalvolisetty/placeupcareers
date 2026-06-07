"""Download and normalize official visa sponsor/employer datasets.

These datasets are verification layers, not job postings. They tell PlaceUp
which employers are known sponsors in each country so the Visa Tracker and
job-scraper company discovery can work from official data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.services.global_visa_rules import COUNTRY_RULES

logger = logging.getLogger(__name__)

UK_SPONSOR_PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
CANADA_LMIA_PACKAGE = "https://open.canada.ca/data/api/action/package_show?id=90fed587-1364-4f33-a9ee-208181dc0b97"
NL_IND_PAGE = "https://ind.nl/en/public-register-recognised-sponsors/public-register-work"
DOL_LCA_PAGE = "https://www.dol.gov/agencies/eta/foreign-labor/performance"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _int(value: Any) -> int:
    try:
        raw = re.sub(r"[^0-9.-]", "", str(value or ""))
        return int(float(raw)) if raw else 0
    except Exception:
        return 0


def _sponsor_id(country: str, source: str, record_id: str) -> str:
    seed = f"{country}|{source}|{record_id}".lower()
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:24]


def _field(row: dict[str, Any], *names: str) -> str:
    if not row:
        return ""
    by_norm = {_norm(k): v for k, v in row.items()}
    for name in names:
        wanted = _norm(name)
        if wanted in by_norm:
            return _clean(by_norm[wanted])
    for key, value in by_norm.items():
        if any(_norm(name) in key for name in names):
            return _clean(value)
    return ""


def _row(
    *,
    employer: str,
    country: str,
    visa_route: str,
    source_name: str,
    source_url: str,
    source_record_id: str,
    city: str = "",
    region: str = "",
    postal_code: str = "",
    status: str = "Active",
    approvals: int = 0,
    denials: int = 0,
    total_petitions: int = 0,
    fiscal_year: int = 0,
    data_json: dict | None = None,
) -> dict | None:
    employer = _clean(employer)
    if len(employer) < 2:
        return None
    country = country.upper()
    rule = COUNTRY_RULES.get(country)
    record_id = _clean(source_record_id) or hashlib.sha1(f"{employer}|{city}|{region}|{visa_route}".encode()).hexdigest()
    return {
        "id": _sponsor_id(country, source_name, record_id),
        "employer_name": employer[:400],
        "normalized_name": _norm(employer)[:400],
        "country": country,
        "country_name": (rule.name if rule else country),
        "visa_route": _clean(visa_route)[:160],
        "city": _clean(city)[:160],
        "region": _clean(region)[:160],
        "postal_code": _clean(postal_code)[:80],
        "status": _clean(status)[:80] or "Active",
        "approvals": approvals,
        "denials": denials,
        "total_petitions": total_petitions or approvals + denials,
        "fiscal_year": fiscal_year,
        "source_name": source_name,
        "source_url": source_url,
        "source_record_id": record_id[:180],
        "last_verified_at": datetime.now(timezone.utc),
        "data_json": data_json or {},
    }


async def _get_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    return response.text


def _csv_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    return [dict(row) for row in reader]


async def download_uk_sponsors(client: httpx.AsyncClient) -> list[dict]:
    page = await _get_text(client, UK_SPONSOR_PAGE)
    soup = BeautifulSoup(page, "html.parser")
    links = [
        urljoin(UK_SPONSOR_PAGE, a.get("href", ""))
        for a in soup.find_all("a", href=True)
        if ".csv" in a.get("href", "").lower()
    ]
    if not links:
        logger.warning("UK sponsors: no CSV link found on GOV.UK page")
        return []
    csv_url = links[0]
    rows = _csv_rows(await _get_text(client, csv_url))
    sponsors: list[dict] = []
    for i, raw in enumerate(rows):
        employer = _field(raw, "Organisation Name", "Organization Name", "Sponsor Name")
        route = _field(raw, "Route", "Worker Route", "Tier and Rating") or "Skilled Worker"
        city = _field(raw, "Town/City", "Town", "City")
        region = _field(raw, "County", "Region")
        sponsor = _row(
            employer=employer,
            country="GB",
            visa_route=route,
            source_name="uk_licensed_sponsors",
            source_url=csv_url,
            source_record_id=f"{employer}|{city}|{route}|{i}",
            city=city,
            region=region,
            status="Active",
            data_json={"source": "GOV.UK Register of licensed sponsors"},
        )
        if sponsor:
            sponsors.append(sponsor)
    logger.info("UK sponsors: parsed %s rows", len(sponsors))
    return sponsors


async def download_canada_lmia_sponsors(client: httpx.AsyncClient) -> list[dict]:
    package = (await client.get(CANADA_LMIA_PACKAGE)).json()
    resources = (package.get("result") or {}).get("resources") or []
    csv_resources = [
        r for r in resources
        if str(r.get("format", "")).lower() == "csv" or str(r.get("url", "")).lower().endswith(".csv")
    ]
    if not csv_resources:
        logger.warning("Canada LMIA: no CSV resources found")
        return []
    # Prefer English CSVs and larger files, which usually contain the current
    # positive-LMIA employer list.
    csv_resources.sort(key=lambda r: ("fr" in str(r.get("name", "")).lower(), -int(r.get("size") or 0)))
    url = csv_resources[0].get("url")
    rows = _csv_rows(await _get_text(client, url))
    sponsors: list[dict] = []
    for i, raw in enumerate(rows):
        employer = _field(raw, "Employer", "Employer Name", "Business Name", "Company")
        city = _field(raw, "City", "Location")
        region = _field(raw, "Province", "Province/Territory", "PT", "Region")
        route = _field(raw, "Program Stream", "Stream", "Program") or "LMIA Work Permit"
        fiscal_year = _int(_field(raw, "Year", "Fiscal Year"))
        sponsor = _row(
            employer=employer,
            country="CA",
            visa_route=route,
            source_name="canada_lmia",
            source_url=str(url),
            source_record_id=f"{employer}|{city}|{region}|{route}|{fiscal_year}|{i}",
            city=city,
            region=region,
            status="Approved",
            approvals=1,
            fiscal_year=fiscal_year,
            data_json={"source": "Government of Canada positive LMIA employers"},
        )
        if sponsor:
            sponsors.append(sponsor)
    logger.info("Canada LMIA: parsed %s rows", len(sponsors))
    return sponsors


async def download_nl_ind_sponsors(client: httpx.AsyncClient) -> list[dict]:
    page = await _get_text(client, NL_IND_PAGE)
    soup = BeautifulSoup(page, "html.parser")
    links = [
        urljoin(NL_IND_PAGE, a.get("href", ""))
        for a in soup.find_all("a", href=True)
        if any(ext in a.get("href", "").lower() for ext in (".csv", ".xlsx", ".xls"))
    ]
    sponsors: list[dict] = []
    if links:
        import pandas as pd

        for url in links[:4]:
            try:
                content = await client.get(url)
                content.raise_for_status()
                if url.lower().endswith(".csv"):
                    frames = [pd.read_csv(io.BytesIO(content.content))]
                else:
                    frames = [pd.read_excel(io.BytesIO(content.content))]
                sponsors.extend(_nl_frames_to_rows(frames, url))
            except Exception as exc:
                logger.warning("NL IND: failed to parse %s: %s", url, exc)
    if not sponsors:
        try:
            import pandas as pd

            frames = pd.read_html(page)
            sponsors.extend(_nl_frames_to_rows(frames, NL_IND_PAGE))
        except Exception as exc:
            logger.warning("NL IND: no parseable tables found: %s", exc)
    logger.info("NL IND: parsed %s rows", len(sponsors))
    return sponsors


def _nl_frames_to_rows(frames: list[Any], source_url: str) -> list[dict]:
    sponsors: list[dict] = []
    for frame in frames:
        for i, raw in enumerate(frame.fillna("").to_dict(orient="records")):
            employer = _field(raw, "Name", "Naam", "Organisation", "Organization", "Sponsor")
            route = _field(raw, "Type", "Category", "Categorie") or "Highly Skilled Migrant"
            city = _field(raw, "City", "Plaats")
            sponsor = _row(
                employer=employer,
                country="NL",
                visa_route=route,
                source_name="nl_ind_recognised_sponsors",
                source_url=source_url,
                source_record_id=f"{employer}|{city}|{route}|{i}",
                city=city,
                status="Recognised",
                data_json={"source": "IND Public Register Recognised Sponsors"},
            )
            if sponsor:
                sponsors.append(sponsor)
    return sponsors


async def mirror_us_h1b_sponsors(db) -> list[dict]:
    rows = await db.get_h1b_sponsors(limit=250000)
    sponsors: list[dict] = []
    for raw in rows:
        employer = raw.get("employer_name") or ""
        city = raw.get("city") or ""
        region = raw.get("state") or ""
        fiscal_year = _int(raw.get("fiscal_year"))
        approvals = _int(raw.get("initial_approvals")) + _int(raw.get("continuing_approvals"))
        denials = _int(raw.get("initial_denials")) + _int(raw.get("continuing_denials"))
        sponsor = _row(
            employer=employer,
            country="US",
            visa_route="H-1B",
            source_name="uscis_h1b",
            source_url="https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub",
            source_record_id=str(raw.get("id") or f"{employer}|{city}|{region}|{fiscal_year}"),
            city=city,
            region=region,
            postal_code=raw.get("zip_code") or "",
            status="Active" if approvals else "Historical",
            approvals=approvals,
            denials=denials,
            total_petitions=_int(raw.get("total_petitions")) or approvals + denials,
            fiscal_year=fiscal_year,
            data_json={"source": "USCIS H-1B Employer Data Hub", **(raw.get("data_json") or {})},
        )
        if sponsor:
            sponsors.append(sponsor)
    logger.info("US H1B mirror: prepared %s sponsor rows", len(sponsors))
    return sponsors


async def import_global_visa_sponsors(db, *, force_h1b: bool = False) -> dict[str, int]:
    from app.services.h1b_excel_importer import import_h1b_excel

    await import_h1b_excel(db, force=force_h1b)
    counts: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        source_tasks = {
            "US": mirror_us_h1b_sponsors(db),
            "GB": download_uk_sponsors(client),
            "CA": download_canada_lmia_sponsors(client),
            "NL": download_nl_ind_sponsors(client),
        }
        for country, task in source_tasks.items():
            try:
                rows = await task
                counts[country] = await db.upsert_visa_sponsors(rows) if rows else 0
            except Exception as exc:
                counts[country] = 0
                logger.warning("Visa sponsor import skipped country=%s error=%s", country, exc)
    return counts
