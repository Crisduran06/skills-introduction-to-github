"""City of Oakland Contract Opportunities connector.

Public URL: https://apps.oaklandca.gov/ContractOpportunities/Opportunities
Custom ASP.NET / Oracle iSupplier frontend — listing appears to be server-rendered.
Individual opportunity: https://apps.oaklandca.gov/ContractOpportunities/Opportunity?Id=N
NOTE: If the page is JS-rendered (React/Angular), fetch_current_projects returns [].
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import SourceConnector
from app.schemas import ProjectIn

LISTING_URL = "https://apps.oaklandca.gov/ContractOpportunities/Opportunities"
DETAIL_BASE = "https://apps.oaklandca.gov/ContractOpportunities/Opportunity?Id="
AGENCY = "City of Oakland"
CITY = "Oakland"
COUNTY = "Alameda"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BidIntel/1.0; +https://github.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


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


def _parse_page(html: str) -> list[ProjectIn]:
    projects: list[ProjectIn] = []
    soup = BeautifulSoup(html, "lxml")

    # Check if the page is an SPA shell (very little content)
    body_text = soup.get_text(strip=True)
    if len(body_text) < 200:
        return projects  # JS-rendered, nothing to parse

    # Try table
    table = (
        soup.find("table", id=re.compile(r"opportunit|contract|bid|grid", re.I))
        or soup.find("table", class_=re.compile(r"opportunit|contract|bid|grid|table", re.I))
        or soup.find("table")
    )

    if table:
        rows = table.find_all("tr")
        if len(rows) >= 2:
            header_cells = rows[0].find_all(["th", "td"])
            headers = [c.get_text(strip=True).lower() for c in header_cells]

            def _col_idx(*kws: str) -> Optional[int]:
                for kw in kws:
                    for i, h in enumerate(headers):
                        if kw in h:
                            return i
                return None

            idx_num = _col_idx("number", "id", "opportunity", "contract")
            idx_title = _col_idx("title", "description", "name", "project")
            idx_dept = _col_idx("department", "dept", "division")
            idx_due = _col_idx("close", "due", "date", "deadline")

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

                ext_id = cells[idx_num].get_text(strip=True) if idx_num is not None and idx_num < len(cells) else ""
                due_raw = cells[idx_due].get_text(strip=True) if idx_due is not None and idx_due < len(cells) else ""
                dept = cells[idx_dept].get_text(strip=True) if idx_dept is not None and idx_dept < len(cells) else ""

                if not due_raw:
                    for cell in cells:
                        txt = cell.get_text(strip=True)
                        if re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", txt):
                            due_raw = txt
                            break

                if not href:
                    id_match = re.search(r"\b(\d+)\b", ext_id)
                    if id_match:
                        href = DETAIL_BASE + id_match.group(1)

                projects.append(ProjectIn(
                    external_id=ext_id or None,
                    project_name=title,
                    agency_owner=f"{AGENCY} — {dept}" if dept else AGENCY,
                    location_city=CITY,
                    location_county=COUNTY,
                    bid_due_date=_parse_date(due_raw),
                    source_url=href if href.startswith("http") else LISTING_URL,
                    status="open",
                    is_archived=False,
                ))

    # Fallback: scan all links for opportunity URLs
    if not projects:
        seen: set[str] = set()
        for a in soup.find_all("a", href=re.compile(r"Opportunity\?Id=|opportunity", re.I)):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or title in seen or len(title) < 4:
                continue
            seen.add(title)

            id_match = re.search(r"Id=(\d+)", href)
            ext_id = id_match.group(1) if id_match else ""

            parent_text = ""
            for parent in a.parents:
                t = parent.get_text(" ", strip=True)
                if 10 < len(t) < 500:
                    parent_text = t
                    break

            date_match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", parent_text)
            due_raw = date_match.group(0) if date_match else ""

            full_href = href if href.startswith("http") else "https://apps.oaklandca.gov" + href

            projects.append(ProjectIn(
                external_id=ext_id or None,
                project_name=title,
                agency_owner=AGENCY,
                location_city=CITY,
                location_county=COUNTY,
                bid_due_date=_parse_date(due_raw),
                source_url=full_href,
                status="open",
                is_archived=False,
            ))

    return projects


class OaklandConnector(SourceConnector):
    name = "Oakland Capital Contracts"
    key = "oakland"
    platform_type = "public_page"
    supports_current_bids = True
    supports_archives = False

    def fetch_current_projects(self) -> list[ProjectIn]:
        try:
            resp = httpx.get(LISTING_URL, headers=HEADERS, timeout=20, follow_redirects=True)
            resp.raise_for_status()
        except Exception:
            return []
        return _parse_page(resp.text)

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_url"] = LISTING_URL
        try:
            projects = self.fetch_current_projects()
            d["status"] = "ok"
            d["projects_found"] = len(projects)
            d["sample"] = projects[0].project_name if projects else None
            if not projects:
                d["note"] = "Page may be JS-rendered (SPA) — zero results returned"
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d
