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
SFPUC_DETAIL_BASE = "https://webapps.sfpuc.org/bids/"
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
                         agency: str, city: str, county: str) -> list[ProjectIn]:
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

        if not title or len(title) < 4:
            continue

        contract_num = cells[idx_num].get_text(strip=True) if idx_num is not None and idx_num < len(cells) else ""
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
            status="open",
            is_archived=False,
        ))

    return projects


def _fetch_sfpuc() -> list[ProjectIn]:
    try:
        resp = httpx.get(SFPUC_URL, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_aspnet_table(soup, SFPUC_URL, SFPUC_DETAIL_BASE,
                                SFPUC_AGENCY, SFPUC_CITY, SFPUC_COUNTY)


def _fetch_sfdpw() -> list[ProjectIn]:
    try:
        resp = httpx.get(SFDPW_URL, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_aspnet_table(soup, SFDPW_URL, SFDPW_URL,
                                SFDPW_AGENCY, SFDPW_CITY, SFDPW_COUNTY)


class SfpucConnector(SourceConnector):
    """SFPUC construction bid connector."""
    name = "SFPUC / SF Bids"
    key = "sfpuc"
    platform_type = "public_page"
    supports_current_bids = True
    supports_archives = False

    def fetch_current_projects(self) -> list[ProjectIn]:
        return _fetch_sfpuc()

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
    supports_archives = False

    def fetch_current_projects(self) -> list[ProjectIn]:
        return _fetch_sfdpw()

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
