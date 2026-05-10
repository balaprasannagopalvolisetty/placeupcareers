"""
PlaceUp Career — H1B Data Service

Aggregates H1B / LCA data from multiple public sources:

  Source                URL                      Stability  Coverage (years)
  ────────────────────────────────────────────────────────────────────────────
  USCIS H-1B Hub CSV    uscis.gov/tools/...      High       FY2009 → FY2024
  DOL FLC Disclosure    dol.gov/agencies/eta     High       FY2008 → present
  h1bdata.info          h1bdata.info             Medium     FY2002 → present
  myVisaJobs            myvisajobs.com           Medium     FY2009 → present
  h1bgrader             h1bgrader.com            Low        FY2014 → present
  h1data                h1data.info              Low        FY2009 → present
  flcdatacenter         flcdatacenter.com        Medium     mirrors DOL data

The USCIS CSV (downloadable annually from uscis.gov) is the official primary
source of truth. The aggregator websites are convenience layers — useful for
enrichment but unstable. Each scraper degrades gracefully on error so a single
failure never breaks the pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from app.models.visa import H1BSalaryData, H1BSponsor

logger = logging.getLogger(__name__)


COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ─── h1bdata.info Scraper ─────────────────────────────────────

async def search_h1b_salaries(
    employer: Optional[str] = None,
    job_title: Optional[str] = None,
    city: Optional[str] = None,
    year: int = 2024,
) -> list[H1BSalaryData]:
    """Search H1B salary data from h1bdata.info.

    Scrapes h1bdata.info for Labor Condition Application (LCA) salary data,
    filtered by employer, job title, and city.
    """
    base_url = "https://h1bdata.info/index.php"
    params: dict[str, str] = {}
    if employer:
        params["em"] = employer
    if job_title:
        params["job"] = job_title
    if city:
        params["city"] = city
    if year:
        params["year"] = str(year)

    if not params:
        logger.warning("H1B search: No search parameters provided")
        return []

    try:
        async with httpx.AsyncClient(timeout=20.0, headers=COMMON_HEADERS) as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("H1B salary search error: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", {"id": "myTable"})
    if not table:
        logger.info("H1B search: No results table found")
        return []

    rows = table.find_all("tr")[1:]
    results: list[H1BSalaryData] = []
    for row in rows[:200]:
        cols = row.find_all("td")
        if len(cols) < 6:
            continue
        try:
            salary_text = cols[3].get_text(strip=True).replace(",", "").replace("$", "")
            salary = float(salary_text) if salary_text else None
            results.append(H1BSalaryData(
                employer=cols[0].get_text(strip=True),
                job_title=cols[1].get_text(strip=True),
                location=cols[2].get_text(strip=True),
                base_salary=salary,
                case_count=1,
                year=year,
            ))
        except (ValueError, IndexError) as exc:
            logger.debug("H1B: skip row: %s", exc)

    logger.info("h1bdata.info: %s rows", len(results))
    return results


# ─── myVisaJobs.com Scraper ────────────────────────────────────

async def search_visa_sponsors(
    company: Optional[str] = None,
    job_title: Optional[str] = None,
) -> list[H1BSponsor]:
    """Search for H1B visa sponsors on myVisaJobs.com."""
    base_url = "https://www.myvisajobs.com/Search_Visa_Sponsor.aspx"
    params: dict[str, str] = {}
    if company:
        params["CO"] = company
    if job_title:
        params["JT"] = job_title

    try:
        async with httpx.AsyncClient(timeout=20.0, headers=COMMON_HEADERS) as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("myVisaJobs error: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", class_="tbl") or soup.find("table", {"id": "MainContent_gvResults"})
    if not table:
        logger.info("myVisaJobs: No results table found")
        return []

    rows = table.find_all("tr")[1:]
    results: list[H1BSponsor] = []
    for row in rows[:100]:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue
        try:
            employer_name = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            if not employer_name:
                continue
            petition_text = cols[2].get_text(strip=True) if len(cols) > 2 else "0"
            petition_count = int(re.sub(r"[^\d]", "", petition_text) or "0")
            city_state = cols[3].get_text(strip=True) if len(cols) > 3 else ""
            city = ""
            state = ""
            if "," in city_state:
                parts = city_state.split(",")
                city = parts[0].strip()
                state = parts[1].strip() if len(parts) > 1 else ""
            results.append(H1BSponsor(
                id=f"mvj_{employer_name[:20]}",
                employer_name=employer_name,
                city=city,
                state=state,
                total_petitions=petition_count,
            ))
        except (ValueError, IndexError) as exc:
            logger.debug("myVisaJobs: skip row: %s", exc)

    logger.info("myVisaJobs: %s sponsors", len(results))
    return results


async def myvisajobs_top_sponsors(year: int = 2024, limit: int = 500) -> list[H1BSponsor]:
    """Fetch the myVisaJobs annual top sponsors leaderboard.

    URL pattern: https://www.myvisajobs.com/Reports/{year}-H1B-Visa-Sponsor.aspx
    Best-effort — site HTML changes occasionally.
    """
    url = f"https://www.myvisajobs.com/Reports/{year}-H1B-Visa-Sponsor.aspx"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=COMMON_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("myVisaJobs top %s: %s", year, exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", class_="tbl")
    if not table:
        return []

    rows: list[H1BSponsor] = []
    for tr in table.find_all("tr")[1:limit + 1]:
        cols = [c.get_text(strip=True) for c in tr.find_all("td")]
        if len(cols) < 3:
            continue
        try:
            employer = cols[1]
            petition_count = int(re.sub(r"[^\d]", "", cols[2]) or "0")
            rows.append(H1BSponsor(
                id=f"mvj_top_{year}_{employer[:30]}",
                employer_name=employer,
                total_petitions=petition_count,
                fiscal_year=year,
            ))
        except (ValueError, IndexError) as exc:
            logger.debug("myVisaJobs top: skip row: %s", exc)

    logger.info("myVisaJobs top sponsors %s: %s rows", year, len(rows))
    return rows


# ─── h1bgrader.com Scraper (best-effort) ──────────────────────

async def h1bgrader_top_sponsors(year: int = 2024, limit: int = 500) -> list[H1BSponsor]:
    """Best-effort scrape of h1bgrader.com top sponsors leaderboard.

    URL pattern: https://h1bgrader.com/h1b-sponsors?year={year}
    The site uses dynamic rendering — without JS we may get an empty shell.
    """
    url = "https://h1bgrader.com/h1b-sponsors"
    params = {"year": str(year), "page": "1", "size": str(min(limit, 500))}
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=COMMON_HEADERS, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("h1bgrader %s: %s", year, exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    sponsors: list[H1BSponsor] = []

    # Heuristic: look for <a href="/sponsor/..."> in any table-like list
    for link in soup.select("a[href*='/sponsor/'], a[href*='/h1b-sponsor/']")[:limit]:
        name = link.get_text(strip=True)
        if not name or name.lower() in {"view", "details", "more"}:
            continue
        sponsors.append(H1BSponsor(
            id=f"hbg_{year}_{name[:30]}",
            employer_name=name,
            fiscal_year=year,
        ))

    # Deduplicate within the page
    seen: set[str] = set()
    deduped: list[H1BSponsor] = []
    for s in sponsors:
        key = s.employer_name.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)

    logger.info("h1bgrader %s: %s sponsors (best-effort)", year, len(deduped))
    return deduped


# ─── h1data.info Scraper (best-effort) ────────────────────────

async def h1data_top_sponsors(year: int = 2024, limit: int = 500) -> list[H1BSponsor]:
    """Best-effort scrape of h1data.info."""
    url = "https://h1data.info/sponsors"
    params = {"year": str(year), "limit": str(min(limit, 500))}
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=COMMON_HEADERS, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("h1data %s: %s", year, exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    sponsors: list[H1BSponsor] = []

    for table in soup.find_all("table"):
        for tr in table.find_all("tr")[1:limit + 1]:
            cols = [c.get_text(strip=True) for c in tr.find_all("td")]
            if not cols or len(cols) < 2:
                continue
            employer = cols[1] if len(cols) > 2 else cols[0]
            if not employer:
                continue
            try:
                count_col = cols[2 if len(cols) > 2 else -1]
                petition_count = int(re.sub(r"[^\d]", "", count_col) or "0")
            except (ValueError, IndexError):
                petition_count = 0
            sponsors.append(H1BSponsor(
                id=f"h1d_{year}_{employer[:30]}",
                employer_name=employer,
                total_petitions=petition_count,
                fiscal_year=year,
            ))

    logger.info("h1data %s: %s sponsors (best-effort)", year, len(sponsors))
    return sponsors[:limit]


# ─── flcdatacenter.com / DOL FLC fallback ─────────────────────

DOL_FLC_DISCLOSURE_URL = "https://www.dol.gov/agencies/eta/foreign-labor/performance"


async def flc_disclosure_links(quarter: str = "Q4", year: int = 2024) -> list[str]:
    """Return downloadable LCA disclosure file URLs from DOL OFLC.

    DOL publishes the underlying disclosure data quarterly. flcdatacenter.com
    is a UI built on top of the same data — we go to the source for stability.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=COMMON_HEADERS, follow_redirects=True) as client:
            response = await client.get(DOL_FLC_DISCLOSURE_URL)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("DOL FLC index: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    links: list[str] = []
    needle = f"{quarter}_FY{year}".lower()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if "h-1b" in text and (needle in text or needle in href.lower() or str(year) in href):
            full = href if href.startswith("http") else f"https://www.dol.gov{href}"
            links.append(full)

    logger.info("DOL FLC: %s links for %s %s", len(links), quarter, year)
    return links


async def flcdatacenter_employer_lookup(employer: str, year: int = 2024) -> list[H1BSalaryData]:
    """Best-effort lookup against flcdatacenter.com (built on DOL data).

    flcdatacenter is the public web UI for DOL FLC disclosure data; their HTML
    is fragile, so we degrade to USCIS / h1bdata.info if it fails.
    """
    if not employer:
        return []
    url = "https://www.flcdatacenter.com/CaseH1B.aspx"
    params = {"Year": str(year), "EmpName": employer}
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=COMMON_HEADERS, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("flcdatacenter %s: %s", employer, exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", id=re.compile(r"gv|grid|results", re.I)) or soup.find("table")
    if not table:
        return []

    results: list[H1BSalaryData] = []
    for row in table.find_all("tr")[1:50]:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 4:
            continue
        try:
            wage = float(re.sub(r"[^\d.]", "", cols[3]) or "0") or None
            results.append(H1BSalaryData(
                employer=cols[0],
                job_title=cols[1] if len(cols) > 1 else "",
                location=cols[2] if len(cols) > 2 else "",
                base_salary=wage,
                case_count=1,
                year=year,
            ))
        except (ValueError, IndexError):
            continue

    logger.info("flcdatacenter %s: %s rows", employer, len(results))
    return results


# ─── USCIS H-1B CSV Importer ──────────────────────────────────

async def import_uscis_csv(file_path: str) -> list[H1BSponsor]:
    """Import H1B sponsor data from USCIS annual CSV file.

    The USCIS H-1B Employer Data Hub provides CSV files with petition data
    for 4M+ records dating back to FY2009. The schema varies year to year;
    this importer normalizes the column names heuristically.
    """
    try:
        import pandas as pd

        df = pd.read_csv(file_path, encoding="utf-8-sig", low_memory=False)
    except ImportError:
        logger.error("pandas not installed. Run: pip install pandas")
        return []
    except FileNotFoundError:
        logger.error("USCIS CSV file not found: %s", file_path)
        return []
    except Exception as exc:
        logger.error("USCIS CSV import error: %s", exc)
        return []

    col_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if "employer" in col_lower or "petitioner" in col_lower:
            col_map[col] = "employer_name"
        elif "initial" in col_lower and "approv" in col_lower:
            col_map[col] = "initial_approvals"
        elif "initial" in col_lower and "deni" in col_lower:
            col_map[col] = "initial_denials"
        elif "continu" in col_lower and "approv" in col_lower:
            col_map[col] = "continuing_approvals"
        elif "continu" in col_lower and "deni" in col_lower:
            col_map[col] = "continuing_denials"
        elif "fiscal" in col_lower or col_lower == "year":
            col_map[col] = "fiscal_year"
        elif "city" in col_lower:
            col_map[col] = "city"
        elif col_lower == "state":
            col_map[col] = "state"
        elif "zip" in col_lower:
            col_map[col] = "zip_code"

    df = df.rename(columns=col_map)

    sponsors: list[H1BSponsor] = []
    for _, row in df.iterrows():
        try:
            employer = str(row.get("employer_name", "")).strip()
            if not employer or employer.lower() == "nan":
                continue
            ia = int(row.get("initial_approvals", 0) or 0)
            id_ = int(row.get("initial_denials", 0) or 0)
            ca = int(row.get("continuing_approvals", 0) or 0)
            cd = int(row.get("continuing_denials", 0) or 0)
            sponsors.append(H1BSponsor(
                id=f"uscis_{employer[:20]}_{row.get('fiscal_year', '')}",
                employer_name=employer,
                city=str(row.get("city", "")).strip(),
                state=str(row.get("state", "")).strip(),
                zip_code=str(row.get("zip_code", "")).strip(),
                initial_approvals=ia,
                initial_denials=id_,
                continuing_approvals=ca,
                continuing_denials=cd,
                total_petitions=ia + id_ + ca + cd,
                fiscal_year=int(row.get("fiscal_year", 0) or 0),
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("USCIS CSV: skip row: %s", exc)

    logger.info("USCIS import: %s sponsor records", len(sponsors))
    return sponsors




# ─── h1bdata.info /topcompanies leaderboard (most stable source) ──────────

async def h1bdata_top_companies(limit: int = 500) -> list[H1BSponsor]:
    """Scrape https://h1bdata.info/topcompanies.php for the canonical top H1B sponsor list.

    Adopted from github.com/praneethravuri/jobs-tools — most stable HTML of all
    the H1B leaderboard sites because it's a simple static table.
    """
    url = "https://h1bdata.info/topcompanies.php"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=COMMON_HEADERS, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("h1bdata topcompanies: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    sponsors: list[H1BSponsor] = []
    table = soup.find("table") or soup.find("table", {"id": "myTable"})
    if not table:
        return []

    for tr in table.find_all("tr")[1:limit + 1]:
        cols = [c.get_text(strip=True) for c in tr.find_all("td")]
        if len(cols) < 2:
            continue
        try:
            employer = cols[0] if not cols[0].isdigit() else cols[1]
            count_col = cols[1] if not cols[0].isdigit() else (cols[2] if len(cols) > 2 else "0")
            petition_count = int(re.sub(r"[^\d]", "", count_col) or "0")
            if not employer or not petition_count:
                continue
            sponsors.append(H1BSponsor(
                id=f"h1bdata_top_{employer[:30]}",
                employer_name=employer,
                total_petitions=petition_count,
            ))
        except (ValueError, IndexError) as exc:
            logger.debug("h1bdata topcompanies: skip row: %s", exc)

    logger.info("h1bdata topcompanies: %s sponsors", len(sponsors))
    return sponsors[:limit]


# ─── Aggregator: build a unified 2022-2026 sponsor list ───────

async def build_recent_sponsors(
    years: tuple[int, ...] = (2022, 2023, 2024, 2025, 2026),
    *,
    per_year_limit: int = 500,
    uscis_csv_paths: Optional[dict[int, str]] = None,
) -> list[H1BSponsor]:
    """Aggregate H1B sponsor records across 2022–2026 from all available sources.

    Pulls from:
      - USCIS CSV (if provided via uscis_csv_paths={year: path})
      - myvisajobs leaderboard
      - h1bgrader leaderboard (best-effort)
      - h1data leaderboard (best-effort)

    Returns a deduplicated list of H1BSponsor objects (key = employer name lower-cased).
    """
    uscis_csv_paths = uscis_csv_paths or {}
    all_records: list[H1BSponsor] = []

    # 1. USCIS CSV per year if available locally
    for year, path in uscis_csv_paths.items():
        try:
            records = await import_uscis_csv(path)
            for r in records:
                if not r.fiscal_year:
                    r.fiscal_year = year
            all_records.extend(records)
        except Exception as exc:  # noqa: BLE001
            logger.warning("USCIS %s import skipped: %s", year, exc)

    # 2. Leaderboards (best effort, run concurrently)
    leaderboard_tasks = []
    for year in years:
        leaderboard_tasks.append(myvisajobs_top_sponsors(year=year, limit=per_year_limit))
        leaderboard_tasks.append(h1bdata_top_companies(limit=per_year_limit))
        leaderboard_tasks.append(h1bgrader_top_sponsors(year=year, limit=per_year_limit))
        leaderboard_tasks.append(h1data_top_sponsors(year=year, limit=per_year_limit))

    leaderboard_results = await asyncio.gather(*leaderboard_tasks, return_exceptions=True)
    for result in leaderboard_results:
        if isinstance(result, Exception):
            logger.warning("Leaderboard task failed: %s", result)
            continue
        if isinstance(result, list):
            all_records.extend(result)

    # Dedupe by lower-cased employer name, keep highest petition count
    by_name: dict[str, H1BSponsor] = {}
    for record in all_records:
        key = record.employer_name.lower().strip()
        if not key:
            continue
        if key not in by_name or record.total_petitions > by_name[key].total_petitions:
            by_name[key] = record

    deduped = sorted(by_name.values(), key=lambda r: r.total_petitions, reverse=True)
    logger.info("Aggregator: %s unique sponsors across years %s", len(deduped), years)
    return deduped


# ─── Employer Verification ─────────────────────────────────────

async def verify_employer_h1b(employer_name: str) -> dict[str, Any]:
    """Verify an employer's H1B sponsorship history.

    Combines data from all available sources to build a comprehensive
    employer verification profile.
    """
    salary_data = await search_h1b_salaries(employer=employer_name)
    sponsor_data = await search_visa_sponsors(company=employer_name)
    flc_data = await flcdatacenter_employer_lookup(employer=employer_name)

    salaries = [s.base_salary for s in salary_data + flc_data if s.base_salary]
    avg_salary = sum(salaries) / len(salaries) if salaries else None
    total_petitions = sum(s.total_petitions for s in sponsor_data)
    is_verified = bool(salary_data or sponsor_data or flc_data)

    return {
        "employer": employer_name,
        "is_verified_sponsor": is_verified,
        "total_lca_records": len(salary_data) + len(flc_data),
        "total_petitions": total_petitions,
        "average_salary": round(avg_salary, 0) if avg_salary else None,
        "salary_data": (salary_data + flc_data)[:10],
        "sponsor_data": sponsor_data[:5],
        "sources_checked": ["h1bdata.info", "myVisaJobs.com", "flcdatacenter.com"],
        "checked_at": datetime.utcnow().isoformat(),
    }
