"""SFPUC and SF Public Works connectors.

SFPUC public bid listing (richest public data — shows estimates):
  https://webapps.sfpuc.org/bids/bidlist.aspx?bidtype=5  (construction)

SF Public Works bid opportunities:
  https://bidopportunities.apps.sfdpw.org/

Both are ASP.NET server-rendered pages — no JS required, no login for listing.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import SourceConnector
from app.schemas import ProjectIn

# SFPUC
SFPUC_URL = "https://webapps.sfpuc.org/bids/bidlist.aspx?bidtype=5"
SFPUC_AWARDS_URLS = [
    "https://webapps.sfpuc.org/bids/bidlist.aspx?bidtype=5&mode=awarded",
    "https://webapps.sfpuc.org/bids/bidlist.aspx?bidtype=5&status=closed",
    "https://webapps.sfpuc.org/bids/AwardedBid.aspx?bidtype=5",
]
SFPUC_DETAIL_BASE = "https://webapps.sfpuc.org/bids/"

# SF Public Works archive candidates
SFDPW_ARCHIVE_URLS = [
    "https://bidopportunities.apps.sfdpw.org/?status=closed",
    "https://bidopportunities.apps.sfdpw.org/Closed",
    "https://bidopportunities.apps.sfdpw.org/Archive",
]
SFPUC_AGENCY = "SFPUC"
SFPUC_CITY = "San Francisco"
SFPUC_COUNTY = "San Francisco"

# SF Public Works
SFDPW_URL = "https://bidopportunities.apps.sfdpw.org/"
SFDPW_AGENCY = "SF Public Works"
SFDPW_CITY = "San Francisco"
SFDPW_COUNTY = "San Francisco"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BidIntel/1.0; +https://github.com)"}


def _parse_money(s: str) -> Optional[float]:
    if not s:
        return None
    clean = re.sub(r"[$,\s]", "", s)
    try:
        return float(clean) if clean else None
    except ValueError:
        return None


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _abs_url(href: str, base: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/")


def _parse_aspnet_table(soup: BeautifulSoup, source_url: str, base_url: str,
                         agency: str, city: str, county: str,
                         is_archived: bool = False) -> list[ProjectIn]:
    projects: list[ProjectIn] = []

    # ASP.NET GridView renders as a <table> — often with id containing "GridView"
    table = (
        soup.find("table", id=re.compile(r"GridView|grid|bid", re.I))
        or soup.find("table", class_=re.compile(r"grid|table|bid", re.I))
        or soup.find("table")
    )
    if not table:
        return projects

    rows = table.find_all("tr")
    if len(rows) < 2:
        return projects

    header_cells = rows[0].find_all(["th", "td"])
    headers = [c.get_text(strip=True).lower() for c in header_cells]

    def _col_idx(*kws: str) -> Optional[int]:
        for kw in kws:
            for i, h in enumerate(headers):
                if kw in h:
                    return i
        return None

    idx_num = _col_idx("contract", "bid no", "bid #", "number", "spec")
    idx_title = _col_idx("title", "project", "description", "name")
    idx_estimate = _col_idx("estimat", "cost", "amount", "value")
    idx_due = _col_idx("bid date", "due", "opening", "close", "date")

    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells or len(cells) < 2:
            continue

        title = ""
        href = ""
        if idx_title is not None and idx_title < len(cells):
            tc = cells[idx_title]
            a = tc.find("a")
            title = a.get_text(strip=True) if a else tc.get_text(strip=True)
            href = a.get("href", "") if a else ""
        else:
            for cell in cells:
                a = cell.find("a")
                if a and len(a.get_text(strip=True)) > 5:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    break
            if not title and len(cells) > 1:
                title = cells[1].get_text(strip=True)

        # If we didn't get a detail URL from the title cell, scan the whole
        # row for any link that looks like a project detail page
        if not href:
            for cell in cells:
                for a in cell.find_all("a", href=True):
                    h = a.get("href", "")
                    if any(kw in h.lower() for kw in ("detail", "caseload", "project", "bid", "opportunity")):
                        href = h
                        break
                if href:
                    break

        if not title or len(title) < 4:
            continue

        contract_num = cells[idx_num].get_text(strip=True) if idx_num is not None and idx_num < len(cells) else ""
        # Discard values that look like category labels rather than real IDs
        if contract_num and not re.search(r'\d', contract_num):
            contract_num = ""
        estimate_raw = cells[idx_estimate].get_text(strip=True) if idx_estimate is not None and idx_estimate < len(cells) else ""
        due_raw = cells[idx_due].get_text(strip=True) if idx_due is not None and idx_due < len(cells) else ""

        if not due_raw:
            for cell in cells:
                txt = cell.get_text(strip=True)
                if re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", txt):
                    due_raw = txt
                    break

        projects.append(ProjectIn(
            external_id=contract_num or None,
            project_name=title,
            agency_owner=agency,
            location_city=city,
            location_county=county,
            bid_due_date=_parse_date(due_raw),
            engineer_estimate=_parse_money(estimate_raw),
            source_url=_abs_url(href, base_url) or source_url,
            status="awarded" if is_archived else "open",
            is_archived=is_archived,
        ))

    return projects


def _fetch_sfpuc(is_archived: bool = False, url: str = SFPUC_URL) -> list[ProjectIn]:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_aspnet_table(soup, url, SFPUC_DETAIL_BASE,
                                SFPUC_AGENCY, SFPUC_CITY, SFPUC_COUNTY,
                                is_archived=is_archived)


def _fetch_sfpuc_archives() -> list[ProjectIn]:
    seen: set[str] = set()
    result: list[ProjectIn] = []
    for url in SFPUC_AWARDS_URLS:
        rows = _fetch_sfpuc(is_archived=True, url=url)
        for p in rows:
            key = p.external_id or p.project_name
            if key not in seen:
                seen.add(key)
                result.append(p)
        if result:
            break
    return result


def _fetch_sfdpw(is_archived: bool = False, url: str = SFDPW_URL) -> list[ProjectIn]:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_aspnet_table(soup, url, SFDPW_URL,
                                SFDPW_AGENCY, SFDPW_CITY, SFDPW_COUNTY,
                                is_archived=is_archived)


def _fetch_sfdpw_archives() -> list[ProjectIn]:
    seen: set[str] = set()
    result: list[ProjectIn] = []
    for url in SFDPW_ARCHIVE_URLS:
        rows = _fetch_sfdpw(is_archived=True, url=url)
        for p in rows:
            key = p.external_id or p.project_name
            if key not in seen:
                seen.add(key)
                result.append(p)
        if result:
            break
    return result


SFPUC_PDF_PAGES = [
    "https://webapps.sfpuc.org/bids/bidlist.aspx?bidtype=5",
    "https://www.sfpuc.org/doing-business/sfpuc-contracting-opportunities/construction-contracts",
    "https://sfwater.org/index.aspx?page=588",
]


class SfpucConnector(SourceConnector):
    """SFPUC construction bid connector."""
    name = "SFPUC / SF Bids"
    key = "sfpuc"
    platform_type = "public_page"
    supports_current_bids = True
    supports_archives = True

    def fetch_current_projects(self) -> list[ProjectIn]:
        return _fetch_sfpuc()

    def fetch_archived_projects(self) -> list[ProjectIn]:
        return [p for p, _ in self.fetch_archived_with_results()]

    def fetch_archived_with_results(self) -> list[tuple[ProjectIn, list]]:
        from app.connectors.pdf_extractor import scrape_pdfs_from_page
        # Try HTML status URL variants first
        html = _fetch_sfpuc_archives()
        if html:
            return [(p, []) for p in html]
        # Fall back to PDF extraction from known SFPUC pages
        seen: set[str] = set()
        results = []
        for page_url in SFPUC_PDF_PAGES:
            for project, bid_results in scrape_pdfs_from_page(
                page_url, SFPUC_AGENCY, SFPUC_CITY, SFPUC_COUNTY, max_pdfs=30
            ):
                key = project.external_id or project.project_name
                if key not in seen:
                    seen.add(key)
                    results.append((project, bid_results))
            if results:
                break
        return results

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_url"] = SFPUC_URL
        try:
            projects = self.fetch_current_projects()
            d["status"] = "ok"
            d["projects_found"] = len(projects)
            d["sample"] = projects[0].project_name if projects else None
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d


class SfPublicWorksConnector(SourceConnector):
    """SF Public Works bid opportunities connector."""
    name = "SF Public Works"
    key = "sf_public_works"
    platform_type = "public_page"
    supports_current_bids = True
    supports_archives = True

    def fetch_current_projects(self) -> list[ProjectIn]:
        return _fetch_sfdpw()

    def fetch_archived_projects(self) -> list[ProjectIn]:
        return _fetch_sfdpw_archives()

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_url"] = SFDPW_URL
        try:
            projects = self.fetch_current_projects()
            d["status"] = "ok"
            d["projects_found"] = len(projects)
            d["sample"] = projects[0].project_name if projects else None
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d
