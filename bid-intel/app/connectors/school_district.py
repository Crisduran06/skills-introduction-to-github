"""School district and municipal procurement connectors.

Shared parsing logic covers HTML tables, Drupal/CMS div rows, article tags,
and list items.  Six concrete connector subclasses target Bay-Area agencies.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import SourceConnector
from app.schemas import ProjectIn

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BidIntel/1.0; +https://github.com)"}

_BID_HEADER_KWS = {"bid", "project", "title", "contract", "solicitation",
                   "description", "rfp", "rfq"}


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


def _parse_bids_page(
    html: str,
    source_url: str,
    base_url: str,
    agency: str,
    city: str,
    county: str,
    is_archived: bool = False,
) -> list[ProjectIn]:
    projects: list[ProjectIn] = []
    soup = BeautifulSoup(html, "lxml")

    # Strip non-content chrome before any extraction
    for tag in soup.find_all(["nav", "footer", "header", "aside"]):
        tag.decompose()

    status = "awarded" if is_archived else "open"

    def _make(title: str, href: str, row_text: str) -> Optional[ProjectIn]:
        title = title.strip()
        if len(title) < 8:
            return None
        date_match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", row_text)
        due_raw = date_match.group(0) if date_match else ""
        num_match = re.search(r"\b([A-Z0-9]{2,}-\d+|\d{4,}-\d+)\b", row_text)
        contract_num = num_match.group(0) if num_match else ""
        return ProjectIn(
            external_id=contract_num or None,
            project_name=title,
            agency_owner=agency,
            location_city=city,
            location_county=county,
            bid_due_date=_parse_date(due_raw),
            trade_scope_raw=title,
            source_url=_abs_url(href, base_url) or source_url,
            status=status,
            is_archived=is_archived,
        )

    # Strategy 1: HTML tables with bid-related column headers
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(strip=True).lower() for c in header_cells]
        if not any(any(kw in h for kw in _BID_HEADER_KWS) for h in headers):
            continue

        def _col(*kws: str) -> Optional[int]:
            for kw in kws:
                for i, h in enumerate(headers):
                    if kw in h:
                        return i
            return None

        idx_title = _col("title", "project", "description", "name", "solicitation", "rfp", "rfq", "bid", "contract")
        idx_num = _col("contract", "solicitation", "number", "bid no", "spec")
        idx_due = _col("due", "close", "opening", "date", "award")
        idx_posted = _col("posted", "issued", "advertised", "publish", "listed", "release", "open date")

        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells or len(cells) < 2:
                continue
            title, href = "", ""
            if idx_title is not None and idx_title < len(cells):
                tc = cells[idx_title]
                a = tc.find("a")
                title = a.get_text(strip=True) if a else tc.get_text(strip=True)
                href = a.get("href", "") if a else ""
            if not title:
                for cell in cells:
                    a = cell.find("a")
                    if a and len(a.get_text(strip=True)) >= 8:
                        title = a.get_text(strip=True)
                        href = a.get("href", "")
                        break
            row_text = row.get_text(" ", strip=True)
            contract_num = ""
            if idx_num is not None and idx_num < len(cells):
                cn = cells[idx_num].get_text(strip=True)
                if re.search(r"\b[A-Z0-9]{2,}-\d+|\d{4,}-\d+", cn):
                    contract_num = cn
            if not contract_num:
                m = re.search(r"\b([A-Z0-9]{2,}-\d+|\d{4,}-\d+)\b", row_text)
                contract_num = m.group(0) if m else ""
            due_raw = ""
            if idx_due is not None and idx_due < len(cells):
                due_raw = cells[idx_due].get_text(strip=True)
            if not due_raw:
                m2 = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", row_text)
                due_raw = m2.group(0) if m2 else ""
            posted_raw = cells[idx_posted].get_text(strip=True) if idx_posted is not None and idx_posted < len(cells) else ""
            p = _make(title, href, row_text)
            if p:
                if contract_num:
                    p.external_id = contract_num
                if due_raw:
                    p.bid_due_date = _parse_date(due_raw)
                if posted_raw:
                    p.posted_date = _parse_date(posted_raw)
                projects.append(p)
        if projects:
            return projects

    # Strategy 2: div rows (CMS/Drupal views)
    row_divs = soup.find_all(
        "div",
        class_=re.compile(r"views-row|view-row|bid-row|field-item|result|listing", re.I),
    )
    for row in row_divs:
        a = row.find("a")
        title = a.get_text(strip=True) if a else ""
        href = a.get("href", "") if a else ""
        p = _make(title, href, row.get_text(" ", strip=True))
        if p:
            projects.append(p)
    if projects:
        return projects

    # Strategy 3: article tags
    for article in soup.find_all("article"):
        a = article.find("a")
        title_tag = a or article.find(re.compile(r"h[1-4]"))
        title = title_tag.get_text(strip=True) if title_tag else ""
        href = a.get("href", "") if a else ""
        p = _make(title, href, article.get_text(" ", strip=True))
        if p:
            projects.append(p)
    if projects:
        return projects

    # Strategy 4: list items that look like real bid links
    for li in soup.find_all("li"):
        a = li.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if len(title) < 15:
            continue
        kws = ("bid", "rfp", "rfq", "contract", "solicitation", "project", "award")
        if not any(kw in href.lower() or kw in title.lower() for kw in kws):
            continue
        p = _make(title, href, li.get_text(" ", strip=True))
        if p:
            projects.append(p)

    return projects


def _fetch_bids_page(
    url: str,
    agency: str,
    city: str,
    county: str,
    is_archived: bool = False,
) -> list[ProjectIn]:
    if not url:
        return []
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    # Derive a base URL from the fetched URL for relative href resolution
    parts = url.split("/")
    base_url = "/".join(parts[:3]) if len(parts) >= 3 else url
    return _parse_bids_page(resp.text, url, base_url, agency, city, county, is_archived=is_archived)


class SchoolDistrictConnector(SourceConnector):
    """Base class for school-district and municipal connectors using shared HTML parsing."""

    current_url: str = ""
    archive_url: str = ""
    agency: str = ""
    city: str = ""
    county: str = ""

    supports_current_bids = True
    supports_archives = True
    platform_type = "public_page"

    def fetch_current_projects(self) -> list[ProjectIn]:
        return _fetch_bids_page(self.current_url, self.agency, self.city, self.county)

    def fetch_archived_projects(self) -> list[ProjectIn]:
        if not self.archive_url:
            return []
        return _fetch_bids_page(self.archive_url, self.agency, self.city, self.county, is_archived=True)

    def fetch_archived_with_results(self) -> list[tuple[ProjectIn, list]]:
        projects = self.fetch_archived_projects()
        if projects:
            return [(p, []) for p in projects]
        # Fall back to PDF extraction from the current page
        from app.connectors.pdf_extractor import scrape_pdfs_from_page
        return scrape_pdfs_from_page(self.current_url, self.agency, self.city, self.county, max_pdfs=20)

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_url"] = self.current_url
        try:
            projects = self.fetch_current_projects()
            d["status"] = "ok"
            d["projects_found"] = len(projects)
            d["sample"] = projects[0].project_name if projects else None
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d


# ---------------------------------------------------------------------------
# Concrete connectors
# ---------------------------------------------------------------------------

class SanJoseConnector(SchoolDistrictConnector):
    name = "City of San Jose Procurement"
    key = "san_jose"
    agency = "City of San Jose"
    city = "San Jose"
    county = "Santa Clara"
    current_url = "https://www.sanjoseca.gov/business/doing-business-with-san-jose/purchasing-and-contracts/solicitations"
    archive_url = "https://www.sanjoseca.gov/business/doing-business-with-san-jose/purchasing-and-contracts/solicitations?status=closed"


class SfUnifiedConnector(SchoolDistrictConnector):
    name = "SF Unified School District"
    key = "sfusd"
    agency = "SFUSD"
    city = "San Francisco"
    county = "San Francisco"
    current_url = "https://www.sfusd.edu/services/business-services/purchasing-contracting-and-bidding/bid-opportunities"
    archive_url = ""


class BerkeleyUnifiedConnector(SchoolDistrictConnector):
    name = "Berkeley Unified School District"
    key = "berkeley_unified"
    agency = "Berkeley Unified"
    city = "Berkeley"
    county = "Alameda"
    current_url = "https://www.berkeleyschools.net/departments/general-services/purchasing/bids/"
    archive_url = ""


class SequoiaUnifiedConnector(SchoolDistrictConnector):
    name = "Sequoia Union High School District"
    key = "sequoia_unified"
    agency = "Sequoia UHSD"
    city = "Redwood City"
    county = "San Mateo"
    current_url = "https://www.seq.org/domain/84"
    archive_url = ""


class PleasantonUnifiedConnector(SchoolDistrictConnector):
    name = "Pleasanton Unified School District"
    key = "pleasanton_unified"
    agency = "Pleasanton Unified"
    city = "Pleasanton"
    county = "Alameda"
    current_url = "https://www.pleasantonusd.net/departments/fiscal-services/purchasing/bids-and-rfps"
    archive_url = ""


class EastSideUnionConnector(SchoolDistrictConnector):
    name = "East Side Union High School District"
    key = "east_side_union"
    agency = "East Side Union HSD"
    city = "San Jose"
    county = "Santa Clara"
    current_url = "https://www.esuhsd.org/administration/departments/business-services/contracts-bids.html"
    archive_url = ""
