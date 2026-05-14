"""Mountain View connector — PlanetBids REST API (live) + fixture fallback.

Mountain View uses PlanetBids at https://vendors.planetbids.com/portal/47527/
The Angular SPA calls a JSON REST API that we can query directly with httpx.

Live API: https://vendors.planetbids.com/api/v2/portal/47527/bids/?status=open
Individual bid: https://vendors.planetbids.com/portal/47527/bo/bo-detail?BidID={id}
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import SourceConnector
from app.config import settings
from app.models import Project
from app.schemas import ProjectIn, BidResultIn

PORTAL_ID = "47527"
API_BASE = f"https://vendors.planetbids.com/api/v2/portal/{PORTAL_ID}"
PORTAL_URL = f"https://vendors.planetbids.com/portal/{PORTAL_ID}/bo/bo-search"
DETAIL_URL = f"https://vendors.planetbids.com/portal/{PORTAL_ID}/bo/bo-detail?BidID="

AGENCY = "City of Mountain View"
CITY = "Mountain View"
COUNTY = "Santa Clara"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BidIntel/1.0; +https://github.com)",
    "Accept": "application/json",
    "Referer": PORTAL_URL,
    "Origin": "https://vendors.planetbids.com",
}


def _parse_money(s) -> Optional[float]:
    if not s:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    clean = re.sub(r"[$,\s]", "", str(s))
    try:
        return float(clean) if clean else None
    except ValueError:
        return None


def _parse_date(s) -> Optional[date]:
    if not s:
        return None
    if isinstance(s, date):
        return s
    s = str(s).strip()
    # API returns ISO format: "2026-05-20T17:00:00Z" or "2026-05-20"
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt).date()
        except ValueError:
            continue
    return None


def _bid_to_project(bid: dict) -> Optional[ProjectIn]:
    # PlanetBids API field names (try common variants)
    bid_id = bid.get("bid_id") or bid.get("id") or bid.get("BidId")
    title = (
        bid.get("bid_title") or bid.get("title") or bid.get("BidTitle")
        or bid.get("name") or ""
    )
    if not title:
        return None

    bid_num = (
        bid.get("bid_number") or bid.get("bid_no") or bid.get("BidNumber")
        or bid.get("number") or str(bid_id or "")
    )
    due_raw = (
        bid.get("bid_due_date") or bid.get("due_date") or bid.get("close_date")
        or bid.get("BidDueDate") or bid.get("opening_date")
    )
    prebid_raw = (
        bid.get("prebid_date") or bid.get("pre_bid_date") or bid.get("conference_date")
    )
    estimate_raw = (
        bid.get("estimated_amount") or bid.get("estimate") or bid.get("engineer_estimate")
        or bid.get("budget")
    )
    description = bid.get("description") or bid.get("scope") or ""
    status_raw = str(bid.get("status") or bid.get("bid_status") or "open").lower()
    is_archived = status_raw in ("closed", "awarded", "cancelled", "expired")

    detail_url = DETAIL_URL + str(bid_id) if bid_id else PORTAL_URL

    return ProjectIn(
        external_id=str(bid_num) if bid_num else None,
        project_name=title,
        agency_owner=AGENCY,
        location_city=CITY,
        location_county=COUNTY,
        bid_due_date=_parse_date(due_raw),
        prebid_date=_parse_date(prebid_raw),
        engineer_estimate=_parse_money(estimate_raw),
        description=description,
        trade_scope_raw=description or title,
        source_url=detail_url,
        status="awarded" if is_archived else "open",
        is_archived=is_archived,
    )


def _fetch_api(status: str = "open") -> list[ProjectIn]:
    """Fetch bids from PlanetBids REST API."""
    projects: list[ProjectIn] = []
    page = 1
    while True:
        try:
            resp = httpx.get(
                f"{API_BASE}/bids/",
                params={"status": status, "page": page, "page_size": 50},
                headers=HEADERS,
                timeout=15,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        # Handle list or paginated dict response
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get("results") or data.get("bids") or data.get("data")
                or data.get("items") or []
            )
        else:
            break

        if not items:
            break

        for bid in items:
            p = _bid_to_project(bid)
            if p:
                projects.append(p)

        # Pagination
        if isinstance(data, dict) and data.get("next"):
            page += 1
        else:
            break

    return projects


# ---------------------------------------------------------------------------
# Fixture parser (kept for offline / CI use)
# ---------------------------------------------------------------------------

def _parse_money_str(s: str) -> Optional[float]:
    if not s:
        return None
    clean = re.sub(r"[$,\s]", "", s)
    try:
        return float(clean) if clean else None
    except ValueError:
        return None


def _parse_date_str(s: str) -> Optional[date]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_open_bids(soup: BeautifulSoup) -> list[ProjectIn]:
    projects: list[ProjectIn] = []
    table = soup.find("table", id="open-bids") or soup.find("table")
    if not table:
        return projects

    for row in table.find_all("tr", class_="bid-row"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        bid_num = cells[0].get_text(strip=True) if len(cells) > 0 else ""
        title_cell = cells[1] if len(cells) > 1 else None
        title_link = title_cell.find("a") if title_cell else None
        title = title_link.get_text(strip=True) if title_link else (title_cell.get_text(strip=True) if title_cell else "")

        bid_due_raw = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        prebid_raw = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        estimate_raw = cells[5].get_text(strip=True) if len(cells) > 5 else ""
        description = cells[6].get_text(strip=True) if len(cells) > 6 else ""

        projects.append(ProjectIn(
            external_id=bid_num,
            project_name=title,
            agency_owner=AGENCY,
            location_city=CITY,
            location_county=COUNTY,
            bid_due_date=_parse_date_str(bid_due_raw),
            prebid_date=_parse_date_str(prebid_raw),
            engineer_estimate=_parse_money_str(estimate_raw),
            description=description,
            trade_scope_raw=description,
            source_url=PORTAL_URL,
            status="open",
            is_archived=False,
        ))

    return projects


def _parse_archive_rows(soup: BeautifulSoup) -> list[tuple[ProjectIn, list[BidResultIn]]]:
    results: list[tuple[ProjectIn, list[BidResultIn]]] = []
    table = soup.find("table", id="archived-bids")
    if not table:
        return results

    for row in table.find_all("tr", class_="archive-row"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        bid_num = cells[0].get_text(strip=True)
        title_cell = cells[1]
        title_link = title_cell.find("a")
        title = title_link.get_text(strip=True) if title_link else title_cell.get_text(strip=True)

        opened_raw = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        awarded_to = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        award_amt_raw = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        ee_raw = cells[5].get_text(strip=True) if len(cells) > 5 else ""
        bidders_cell = cells[6] if len(cells) > 6 else None

        project = ProjectIn(
            external_id=bid_num,
            project_name=title,
            agency_owner=AGENCY,
            location_city=CITY,
            location_county=COUNTY,
            bid_due_date=_parse_date_str(opened_raw),
            engineer_estimate=_parse_money_str(ee_raw),
            source_url=PORTAL_URL,
            status="awarded" if awarded_to else "bid_opened",
            is_archived=True,
        )

        bid_results: list[BidResultIn] = []
        if bidders_cell:
            for li in bidders_cell.find_all("li"):
                text = li.get_text(strip=True)
                parts = text.split("—")
                if len(parts) < 2:
                    parts = text.split("-")
                company_name = parts[0].strip() if parts else text
                amount_part = parts[1].strip() if len(parts) > 1 else ""
                amount_match = re.search(r"\$[\d,]+", amount_part)
                amount = _parse_money_str(amount_match.group(0)) if amount_match else None
                is_low = "low bidder" in amount_part.lower()
                is_awarded = "awarded" in amount_part.lower()
                bid_results.append(BidResultIn(
                    listed_as=company_name,
                    bid_amount=amount,
                    is_low_bidder=is_low,
                    is_awarded=is_awarded,
                    result_date=_parse_date_str(opened_raw),
                    source_url=PORTAL_URL,
                ))

        if not bid_results and awarded_to:
            bid_results.append(BidResultIn(
                listed_as=awarded_to,
                bid_amount=_parse_money_str(award_amt_raw),
                is_low_bidder=True,
                is_awarded=True,
                result_date=_parse_date_str(opened_raw),
                source_url=PORTAL_URL,
            ))

        results.append((project, bid_results))

    return results


class MountainViewConnector(SourceConnector):
    name = "Mountain View Official Bids"
    key = "mountain_view"
    platform_type = "public_page"
    supports_current_bids = True
    supports_bid_results = True
    supports_awards = True
    supports_archives = True

    def __init__(self, fixture: bool = False):
        self._fixture = fixture
        self._fixture_path = settings.fixtures_dir / "mountain_view_sample.html"

    def _load_fixture_soup(self) -> BeautifulSoup:
        html = self._fixture_path.read_text(encoding="utf-8")
        return BeautifulSoup(html, "lxml")

    def fetch_current_projects(self) -> list[ProjectIn]:
        if self._fixture:
            return _parse_open_bids(self._load_fixture_soup())
        projects = _fetch_api(status="open")
        if not projects:
            # API unavailable — fall back to fixture data
            projects = _parse_open_bids(self._load_fixture_soup())
        return projects

    def fetch_archived_projects(self) -> list[ProjectIn]:
        if self._fixture:
            return [proj for proj, _ in _parse_archive_rows(self._load_fixture_soup())]
        seen: set[str] = set()
        result = []
        # PlanetBids uses different status strings across portal versions
        for status_val in ("closed", "awarded", "Closed", "Awarded", "past", "complete"):
            for p in _fetch_api(status=status_val):
                key = p.external_id or p.project_name
                if key not in seen:
                    seen.add(key)
                    result.append(p)
            if result:
                break
        return result

    def fetch_archived_with_results(self) -> list[tuple[ProjectIn, list[BidResultIn]]]:
        if self._fixture:
            return _parse_archive_rows(self._load_fixture_soup())
        return [(p, []) for p in self.fetch_archived_projects()]

    def fetch_bid_results(self, project: Project) -> list[BidResultIn]:
        return []

    def fetch_award_info(self, project: Project) -> Optional[dict]:
        return None

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_api"] = f"{API_BASE}/bids/"
        d["portal_url"] = PORTAL_URL
        d["fixture_path"] = str(self._fixture_path)
        d["fixture_exists"] = self._fixture_path.exists()
        try:
            projects = _fetch_api(status="open")
            if projects:
                d["status"] = "ok"
                d["api_projects_found"] = len(projects)
                d["sample"] = projects[0].project_name
            else:
                d["status"] = "api_empty_or_blocked"
                d["note"] = "API returned 0 results — may require session cookie or be blocked"
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d
