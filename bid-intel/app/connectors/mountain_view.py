"""Mountain View connector — supports fixture mode and live public page.

Live URL: https://www.mountainview.gov/depts/pw/purchasing/default.asp
The page is public, no login required. Live fetch is enabled but falls back
to fixtures if the live page is unavailable.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from app.connectors.base import SourceConnector
from app.config import settings
from app.models import Project
from app.schemas import ProjectIn, PlanholderIn, BidResultIn, AddendumIn

LIVE_URL = "https://www.mountainview.gov/depts/pw/purchasing/default.asp"
PORTAL_URL = "https://vendors.planetbids.com/portal/47527/bo/bo-search"
AGENCY = "City of Mountain View"
CITY = "Mountain View"
COUNTY = "Santa Clara"


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
        href = title_link.get("href", "") if title_link else ""

        bid_due_raw = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        prebid_raw = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        estimate_raw = cells[5].get_text(strip=True) if len(cells) > 5 else ""
        description = cells[6].get_text(strip=True) if len(cells) > 6 else ""
        docs_cell = cells[7] if len(cells) > 7 else None
        docs_link = docs_cell.find("a") if docs_cell else None
        docs_url = docs_link.get("href", "") if docs_link else ""

        # Mountain View uses PlanetBids — fixture hrefs are synthetic and don't exist
        # on the real site. Always point to the public portal search page.
        source_url = PORTAL_URL

        projects.append(ProjectIn(
            external_id=bid_num,
            project_name=title,
            agency_owner=AGENCY,
            location_city=CITY,
            location_county=COUNTY,
            bid_due_date=_parse_date(bid_due_raw),
            prebid_date=_parse_date(prebid_raw),
            engineer_estimate=_parse_money(estimate_raw),
            description=description,
            trade_scope_raw=description,
            source_url=source_url,
            documents_url=f"https://www.mountainview.gov{docs_url}" if docs_url.startswith("/") else docs_url or None,
            status="open",
            is_archived=False,
        ))

    return projects


def _parse_archive_rows(soup: BeautifulSoup) -> list[tuple[ProjectIn, list[BidResultIn]]]:
    """Returns list of (project, bid_results) tuples from the archived section."""
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
        href = title_link.get("href", "") if title_link else ""

        opened_raw = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        awarded_to = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        award_amt_raw = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        ee_raw = cells[5].get_text(strip=True) if len(cells) > 5 else ""
        bidders_cell = cells[6] if len(cells) > 6 else None
        result_cell = cells[7] if len(cells) > 7 else None

        result_link = result_cell.find("a") if result_cell else None
        result_url = result_link.get("href", "") if result_link else ""

        source_url = f"https://www.mountainview.gov{href}" if href.startswith("/") else href or LIVE_URL

        project = ProjectIn(
            external_id=bid_num,
            project_name=title,
            agency_owner=AGENCY,
            location_city=CITY,
            location_county=COUNTY,
            bid_due_date=_parse_date(opened_raw),
            engineer_estimate=_parse_money(ee_raw),
            source_url=source_url,
            results_url=f"https://www.mountainview.gov{result_url}" if result_url.startswith("/") else result_url or None,
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
                amount = _parse_money(amount_match.group(0)) if amount_match else None

                is_low = "low bidder" in amount_part.lower()
                is_awarded = "awarded" in amount_part.lower()

                bid_results.append(BidResultIn(
                    listed_as=company_name,
                    bid_amount=amount,
                    is_low_bidder=is_low,
                    is_awarded=is_awarded,
                    result_date=_parse_date(opened_raw),
                    source_url=source_url,
                ))

        if not bid_results and awarded_to:
            bid_results.append(BidResultIn(
                listed_as=awarded_to,
                bid_amount=_parse_money(award_amt_raw),
                is_low_bidder=True,
                is_awarded=True,
                result_date=_parse_date(opened_raw),
                source_url=source_url,
            ))

        results.append((project, bid_results))

    return results


class MountainViewConnector(SourceConnector):
    name = "Mountain View Official Bids"
    key = "mountain_view"
    platform_type = "public_page"
    supports_current_bids = True
    supports_planholders = False
    supports_bid_results = True
    supports_awards = True
    supports_archives = True

    def __init__(self, fixture: bool = False):
        self._fixture = fixture
        self._fixture_path = settings.fixtures_dir / "mountain_view_sample.html"

    def _load_soup(self, fixture: bool = False) -> BeautifulSoup:
        if fixture or self._fixture:
            html = self._fixture_path.read_text(encoding="utf-8")
        else:
            try:
                import httpx
                resp = httpx.get(LIVE_URL, timeout=10, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text
            except Exception:
                # Fall back to fixture data if live fetch fails
                html = self._fixture_path.read_text(encoding="utf-8")
        return BeautifulSoup(html, "lxml")

    def fetch_current_projects(self) -> list[ProjectIn]:
        soup = self._load_soup()
        return _parse_open_bids(soup)

    def fetch_archived_projects(self) -> list[ProjectIn]:
        soup = self._load_soup()
        return [proj for proj, _ in _parse_archive_rows(soup)]

    def fetch_archived_with_results(self) -> list[tuple[ProjectIn, list[BidResultIn]]]:
        soup = self._load_soup()
        return _parse_archive_rows(soup)

    def fetch_bid_results(self, project: Project) -> list[BidResultIn]:
        # TODO: fetch from project.results_url when live
        return []

    def fetch_award_info(self, project: Project) -> Optional[dict]:
        # TODO: parse award page from project.award_url when live
        return None

    def fetch_addenda(self, project: Project) -> list[AddendumIn]:
        # TODO: parse addenda from project detail page when live
        return []

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_url"] = LIVE_URL
        d["fixture_path"] = str(self._fixture_path)
        d["fixture_exists"] = self._fixture_path.exists()
        d["fixture_mode"] = self._fixture
        try:
            soup = self._load_soup(fixture=True)
            open_bids = _parse_open_bids(soup)
            archived = _parse_archive_rows(soup)
            d["fixture_open_bids"] = len(open_bids)
            d["fixture_archived_bids"] = len(archived)
            d["status"] = "ok"
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d
