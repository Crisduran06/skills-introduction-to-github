"""Port of Oakland connector.

Public URL: https://www.portofoakland.com/business/bids-rfp-center/engineering-bids-rfps-rfqs
WordPress CMS — server-rendered HTML, no JS required, no login needed.
Note: BidNet Direct (bidnetdirect.com) is used for formal posting but requires login;
we only scrape the Port's own public WordPress page.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import SourceConnector
from app.schemas import ProjectIn

BIDS_URL = "https://www.portofoakland.com/business/bids-rfp-center/engineering-bids-rfps-rfqs"
HUB_URL = "https://www.portofoakland.com/business/bids-rfp-center"
BASE_URL = "https://www.portofoakland.com"
AGENCY = "Port of Oakland"
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


def _parse_page(html: str, source_url: str) -> list[ProjectIn]:
    projects: list[ProjectIn] = []
    soup = BeautifulSoup(html, "lxml")

    # WordPress typically uses <article> elements or a main content <div>
    # Look for bid entries as links/articles in the main content area
    main = (
        soup.find("main")
        or soup.find("div", class_=re.compile(r"entry-content|page-content|wp-block|content", re.I))
        or soup.find("div", id=re.compile(r"content|main", re.I))
        or soup
    )

    # Try table first
    table = main.find("table")
    if table:
        rows = table.find_all("tr")
        if len(rows) >= 2:
            for row in rows[1:]:
                cells = row.find_all("td")
                if not cells:
                    continue
                a = row.find("a")
                title = a.get_text(strip=True) if a else cells[0].get_text(strip=True)
                href = a.get("href", "") if a else ""

                text = row.get_text(" ", strip=True)
                date_match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", text)
                due_raw = date_match.group(0) if date_match else ""
                num_match = re.search(r"\b([A-Z]+-\d+|\d{4,}-\d+)\b", text)
                ext_id = num_match.group(0) if num_match else ""

                if not title or len(title) < 4:
                    continue
                projects.append(ProjectIn(
                    external_id=ext_id or None,
                    project_name=title,
                    agency_owner=AGENCY,
                    location_city=CITY,
                    location_county=COUNTY,
                    bid_due_date=_parse_date(due_raw),
                    source_url=_abs_url(href) or source_url,
                    status="open",
                    is_archived=False,
                ))
            if projects:
                return projects

    # WordPress list/article fallback — find all links in content area
    seen: set[str] = set()
    for a in main.find_all("a", href=True):
        href = a.get("href", "")
        title = a.get_text(strip=True)

        # Skip nav/menu links and short text
        if len(title) < 8:
            continue
        if any(skip in title.lower() for skip in ("home", "contact", "about", "login", "register", "search")):
            continue
        if title in seen:
            continue

        # Only keep links that look like bid pages (PDF, detail page, or bid-related URL)
        is_bid_link = (
            "bid" in href.lower()
            or "rfp" in href.lower()
            or "rfq" in href.lower()
            or "procurement" in href.lower()
            or href.endswith(".pdf")
            or "bid" in title.lower()
            or "rfp" in title.lower()
            or "contract" in title.lower()
        )
        if not is_bid_link:
            continue

        seen.add(title)

        # Look for a date near the link
        parent_text = ""
        for parent in a.parents:
            text = parent.get_text(" ", strip=True)
            if len(text) < 500:
                parent_text = text
                break

        date_match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", parent_text)
        due_raw = date_match.group(0) if date_match else ""
        num_match = re.search(r"\b([A-Z]+-\d+|\d{4,}-\d+)\b", parent_text)
        ext_id = num_match.group(0) if num_match else ""

        projects.append(ProjectIn(
            external_id=ext_id or None,
            project_name=title,
            agency_owner=AGENCY,
            location_city=CITY,
            location_county=COUNTY,
            bid_due_date=_parse_date(due_raw),
            source_url=_abs_url(href),
            status="open",
            is_archived=False,
        ))

    return projects


def _fetch(url: str) -> list[ProjectIn]:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    return _parse_page(resp.text, url)


class PortOaklandConnector(SourceConnector):
    name = "Port of Oakland"
    key = "port_oakland"
    platform_type = "public_page"
    supports_current_bids = True
    supports_archives = False

    def fetch_current_projects(self) -> list[ProjectIn]:
        return _fetch(BIDS_URL)

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_url"] = BIDS_URL
        try:
            projects = self.fetch_current_projects()
            d["status"] = "ok"
            d["projects_found"] = len(projects)
            d["sample"] = projects[0].project_name if projects else None
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d
