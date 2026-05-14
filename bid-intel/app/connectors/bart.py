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


def _make_project(title: str, href: str, text: str, source_url: str, archived: bool) -> Optional[ProjectIn]:
    if not title or len(title) < 8:
        return None
    date_match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", text)
    due_raw = date_match.group(0) if date_match else ""
    num_match = re.search(r"\b([A-Z]{1,5}-\d{3,}|\d{4,}-\d+)\b", text)
    contract_num = num_match.group(0) if num_match else ""
    return ProjectIn(
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
    )


def _parse_page(html: str, source_url: str, archived: bool = False) -> list[ProjectIn]:
    projects: list[ProjectIn] = []
    soup = BeautifulSoup(html, "lxml")

    # Strategy 1: any HTML table on the page
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        header_cells = rows[0].find_all(["th", "td"]) if rows else []
        headers = [c.get_text(strip=True).lower() for c in header_cells]

        def _col_idx(*kws):
            for kw in kws:
                for i, h in enumerate(headers):
                    if kw in h:
                        return i
            return None

        idx_num = _col_idx("contract", "solicitation", "number", "bid", "spec")
        idx_title = _col_idx("title", "description", "project", "name", "subject")
        idx_due = _col_idx("due", "close", "award", "opening", "date")

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
                    if a and len(a.get_text(strip=True)) > 8:
                        title = a.get_text(strip=True)
                        href = a.get("href", "")
                        break
            contract_num = cells[idx_num].get_text(strip=True) if idx_num is not None and idx_num < len(cells) else ""
            due_raw = cells[idx_due].get_text(strip=True) if idx_due is not None and idx_due < len(cells) else ""
            row_text = row.get_text(" ", strip=True)
            if not due_raw:
                m = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", row_text)
                due_raw = m.group(0) if m else ""
            p = _make_project(title, href, row_text, source_url, archived)
            if p:
                if contract_num:
                    p.external_id = contract_num
                if due_raw:
                    p.bid_due_date = _parse_date(due_raw)
                projects.append(p)
        if projects:
            return projects

    # Strategy 2: Drupal Views div rows (multiple class patterns)
    container = (
        soup.find("div", class_=re.compile(r"view-content|view-procurement|view-awards|field-items", re.I))
        or soup.find("main")
        or soup.find("div", id=re.compile(r"content|main|primary", re.I))
        or soup.find("div", class_="content")
        or soup
    )

    row_divs = container.find_all("div", class_=re.compile(r"views-row|view-row|bid-row|field-item", re.I))
    for row in row_divs:
        a = row.find("a")
        title = a.get_text(strip=True) if a else ""
        href = a.get("href", "") if a else ""
        text = row.get_text(" ", strip=True)
        p = _make_project(title, href, text, source_url, archived)
        if p:
            projects.append(p)
    if projects:
        return projects

    # Strategy 3: article tags (Drupal 8/9)
    for article in container.find_all("article"):
        a = article.find("a")
        title = a.get_text(strip=True) if a else article.find(re.compile(r"h[1-4]"))
        if hasattr(title, "get_text"):
            title = title.get_text(strip=True)
        href = a.get("href", "") if a else ""
        text = article.get_text(" ", strip=True)
        p = _make_project(str(title), href, text, source_url, archived)
        if p:
            projects.append(p)
    if projects:
        return projects

    # Strategy 4: list items in main content (simple bulleted award lists)
    # Exclude nav/footer/sidebar elements first
    for nav in soup.find_all(["nav", "footer", "header"]):
        nav.decompose()
    for li in container.find_all("li"):
        a = li.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        # Must look like an actual bid/contract link, not navigation
        href_lower = href.lower()
        title_lower = title.lower()
        if len(title) < 15:
            continue
        if any(skip in title_lower for skip in ("portal", "login", "register", "home", "contact", "about")):
            continue
        if not any(kw in href_lower or kw in title_lower for kw in
                   ("contract", "award", "bid", "solicitation", "rfp", "rfq", "project")):
            continue
        text = li.get_text(" ", strip=True)
        p = _make_project(title, href, text, source_url, archived)
        if p:
            projects.append(p)

    return projects


def _fetch(url: str, archived: bool = False) -> list[ProjectIn]:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
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
        return [p for p, _ in self.fetch_archived_with_results()]

    def fetch_archived_with_results(self) -> list[tuple[ProjectIn, list]]:
        from app.connectors.pdf_extractor import scrape_pdfs_from_page
        _NAV_WORDS = {"portal", "login", "register", "home", "contact", "about",
                      "procurement portal", "bid portal", "click here", "learn more"}
        html_projects = _fetch(AWARDS_URL, archived=True)
        real = [
            p for p in html_projects
            if len(p.project_name) > 20
            and p.project_name.lower() not in _NAV_WORDS
            and not any(w in p.project_name.lower() for w in ("portal", "login"))
        ]
        if real:
            return [(p, []) for p in real]
        # Fall back to PDF extraction — try awards page and main procurement page
        results = scrape_pdfs_from_page(AWARDS_URL, AGENCY, CITY, COUNTY, max_pdfs=40)
        if not results:
            results = scrape_pdfs_from_page(CURRENT_URL, AGENCY, CITY, COUNTY, max_pdfs=20)
        return results

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
