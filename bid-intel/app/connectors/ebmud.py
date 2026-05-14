"""EBMUD Construction Bids connector.

Public URL: https://construction-bids.ebmud.com/CurrentorFutureBid.aspx?BidMode=Current
ASP.NET WebForms — server-rendered HTML table, no JS required, no login needed.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import SourceConnector
from app.schemas import ProjectIn

CURRENT_URL = "https://construction-bids.ebmud.com/CurrentorFutureBid.aspx?BidMode=Current"
FUTURE_URL = "https://construction-bids.ebmud.com/CurrentorFutureBid.aspx?BidMode=Future"
PAST_URL = "https://construction-bids.ebmud.com/CurrentorFutureBid.aspx?BidMode=Past"
AWARDS_URL = "https://construction-bids.ebmud.com/AwardedBid.aspx"
BASE_URL = "https://construction-bids.ebmud.com"
AGENCY = "EBMUD"
CITY = "Oakland"
COUNTY = "Alameda"
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
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _abs_url(href: str) -> str:
    if not href:
        return ""
    return href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")


def _parse_table(soup: BeautifulSoup, source_url: str, is_archived: bool = False) -> list[ProjectIn]:
    projects: list[ProjectIn] = []

    table = (
        soup.find("table", id=re.compile(r"grid|view", re.I))
        or soup.find("table", class_=re.compile(r"grid|data|bid", re.I))
        or soup.find("table")
    )
    if not table:
        return projects

    rows = table.find_all("tr")
    if len(rows) < 2:
        return projects

    # Detect column positions from header row
    header_cells = rows[0].find_all(["th", "td"])
    headers = [c.get_text(strip=True).lower() for c in header_cells]

    def _col_idx(*keywords: str) -> Optional[int]:
        for kw in keywords:
            for i, h in enumerate(headers):
                if kw in h:
                    return i
        return None

    idx_num = _col_idx("bid", "spec", "number", "contract")
    idx_title = _col_idx("title", "project", "description", "name")
    idx_opening = _col_idx("opening", "bid date", "due", "close")
    idx_prebid = _col_idx("pre-bid", "prebid", "pre bid", "conference")

    for row in rows[1:]:
        cells = row.find_all(["td"])
        if not cells or len(cells) < 2:
            continue

        # Find title — prefer column by header, fall back to first cell with a link
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
            if not title:
                title = cells[1].get_text(strip=True) if len(cells) > 1 else ""

        if not title or title.lower() in {"project title", "description", "bid title", "title"}:
            continue

        bid_num = cells[idx_num].get_text(strip=True) if idx_num is not None and idx_num < len(cells) else ""
        bid_date_raw = cells[idx_opening].get_text(strip=True) if idx_opening is not None and idx_opening < len(cells) else ""
        prebid_raw = cells[idx_prebid].get_text(strip=True) if idx_prebid is not None and idx_prebid < len(cells) else ""

        # Fallback: scan cells for a date pattern
        if not bid_date_raw:
            for cell in cells:
                txt = cell.get_text(strip=True)
                if re.match(r"\d{1,2}/\d{1,2}/\d{4}", txt):
                    bid_date_raw = txt
                    break

        projects.append(ProjectIn(
            external_id=bid_num or None,
            project_name=title,
            agency_owner=AGENCY,
            location_city=CITY,
            location_county=COUNTY,
            bid_due_date=_parse_date(bid_date_raw),
            prebid_date=_parse_date(prebid_raw),
            source_url=_abs_url(href) or source_url,
            status="awarded" if is_archived else "open",
            is_archived=is_archived,
        ))

    return projects


def _fetch(url: str, is_archived: bool = False) -> list[ProjectIn]:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    return _parse_table(BeautifulSoup(resp.text, "lxml"), url, is_archived=is_archived)


class EbmudConnector(SourceConnector):
    name = "EBMUD Construction Bids"
    key = "ebmud"
    platform_type = "public_page"
    supports_current_bids = True
    supports_archives = True

    def fetch_current_projects(self) -> list[ProjectIn]:
        seen: set[str] = set()
        result: list[ProjectIn] = []
        for p in _fetch(CURRENT_URL) + _fetch(FUTURE_URL):
            key = p.external_id or p.project_name
            if key not in seen:
                seen.add(key)
                result.append(p)
        return result

    def fetch_archived_projects(self) -> list[ProjectIn]:
        return [p for p, _ in self.fetch_archived_with_results()]

    def fetch_archived_with_results(self) -> list[tuple[ProjectIn, list]]:
        from app.connectors.pdf_extractor import scrape_pdfs_from_page
        seen: set[str] = set()
        result = []
        # Try the guessed HTML archive URLs first
        for p in _fetch(PAST_URL, is_archived=True) + _fetch(AWARDS_URL, is_archived=True):
            key = p.external_id or p.project_name
            if key not in seen:
                seen.add(key)
                result.append((p, []))
        if result:
            return result
        # Fall back: scan the main EBMUD bids site for PDF links
        for page_url in (CURRENT_URL, BASE_URL + "/"):
            for project, bid_results in scrape_pdfs_from_page(
                page_url, AGENCY, CITY, COUNTY, max_pdfs=30
            ):
                key = project.external_id or project.project_name
                if key not in seen:
                    seen.add(key)
                    result.append((project, bid_results))
            if result:
                break
        return result

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_url"] = CURRENT_URL
        try:
            projects = self.fetch_current_projects()
            d["status"] = "ok"
            d["projects_found"] = len(projects)
            d["sample"] = projects[0].project_name if projects else None
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d
