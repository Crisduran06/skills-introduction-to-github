"""BART Procurement connector.

Public URL: https://www.bart.gov/about/business/procurement/contractsout
Drupal CMS — server-rendered HTML, no JS required, no login needed for listing.
Also scrapes the bid results page for recently awarded contracts.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import SourceConnector
from app.schemas import ProjectIn

CURRENT_URL = "https://www.bart.gov/about/business/procurement/contractsout"
AWARDS_URL = "https://www.bart.gov/about/business/procurement/awards"
BASE_URL = "https://www.bart.gov"
AGENCY = "BART"
CITY = "Oakland"
COUNTY = "Alameda"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BidIntel/1.0; +https://github.com)"}


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


def _abs_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")


def _parse_page(html: str, source_url: str, archived: bool = False) -> list[ProjectIn]:
    projects: list[ProjectIn] = []
    soup = BeautifulSoup(html, "lxml")

    # Drupal Views renders as <div class="view-content"> with table or row divs
    container = (
        soup.find("div", class_=re.compile(r"view-content|view-procurement", re.I))
        or soup.find("div", class_="content")
        or soup
    )

    # Try table first
    table = container.find("table")
    if table:
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

        idx_num = _col_idx("contract", "solicitation", "number", "bid")
        idx_title = _col_idx("title", "description", "project", "name")
        idx_due = _col_idx("due", "close", "opening", "date")
        idx_type = _col_idx("type", "category")

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
                if not title and cells:
                    title = cells[1].get_text(strip=True) if len(cells) > 1 else cells[0].get_text(strip=True)

            if not title or len(title) < 4:
                continue

            contract_num = cells[idx_num].get_text(strip=True) if idx_num is not None and idx_num < len(cells) else ""
            due_raw = cells[idx_due].get_text(strip=True) if idx_due is not None and idx_due < len(cells) else ""
            scope = cells[idx_type].get_text(strip=True) if idx_type is not None and idx_type < len(cells) else ""

            projects.append(ProjectIn(
                external_id=contract_num or None,
                project_name=title,
                agency_owner=AGENCY,
                location_city=CITY,
                location_county=COUNTY,
                bid_due_date=_parse_date(due_raw),
                trade_scope_raw=scope or title,
                source_url=_abs_url(href) or source_url,
                status="awarded" if archived else "open",
                is_archived=archived,
            ))
        return projects

    # Fallback: Drupal view rows as divs
    rows = container.find_all("div", class_=re.compile(r"views-row|view-row|bid-row", re.I))
    for row in rows:
        a = row.find("a")
        title = a.get_text(strip=True) if a else row.get_text(strip=True)[:120]
        href = a.get("href", "") if a else ""

        # Look for a date pattern anywhere in the row text
        text = row.get_text(" ", strip=True)
        date_match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", text)
        due_raw = date_match.group(0) if date_match else ""

        num_match = re.search(r"\b([A-Z]{1,4}-\d{3,}|\d{4,}-\d+)\b", text)
        contract_num = num_match.group(0) if num_match else ""

        if not title or len(title) < 4:
            continue

        projects.append(ProjectIn(
            external_id=contract_num or None,
            project_name=title,
            agency_owner=AGENCY,
            location_city=CITY,
            location_county=COUNTY,
            bid_due_date=_parse_date(due_raw),
            trade_scope_raw=title,
            source_url=_abs_url(href) or source_url,
            status="awarded" if archived else "open",
            is_archived=archived,
        ))

    return projects


def _fetch(url: str, archived: bool = False) -> list[ProjectIn]:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    return _parse_page(resp.text, url, archived=archived)


class BartConnector(SourceConnector):
    name = "BART Procurement"
    key = "bart"
    platform_type = "public_page"
    supports_current_bids = True
    supports_archives = True

    def fetch_current_projects(self) -> list[ProjectIn]:
        return _fetch(CURRENT_URL, archived=False)

    def fetch_archived_projects(self) -> list[ProjectIn]:
        return _fetch(AWARDS_URL, archived=True)

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
