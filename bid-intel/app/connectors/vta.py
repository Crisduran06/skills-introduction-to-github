"""VTA Santa Clara Valley Transportation Authority connector.

VTA uses OpenGov Procurement (React SPA) at:
  https://procurement.opengov.com/portal/vta

The SPA calls a JSON REST API we can query directly — no browser needed.
API: https://procurement.opengov.com/api/v0/solicitations?portal=vta&status=open
Individual: https://procurement.opengov.com/portal/vta/projects/{id}
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

import httpx

from app.connectors.base import SourceConnector
from app.schemas import ProjectIn

PORTAL_SLUG = "vta"
API_BASE = "https://procurement.opengov.com/api/v0"
PORTAL_URL = f"https://procurement.opengov.com/portal/{PORTAL_SLUG}"
DETAIL_BASE = f"https://procurement.opengov.com/portal/{PORTAL_SLUG}/projects/"

AGENCY = "VTA"
CITY = "San Jose"
COUNTY = "Santa Clara"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BidIntel/1.0; +https://github.com)",
    "Accept": "application/json",
    "Referer": PORTAL_URL,
    "Origin": "https://procurement.opengov.com",
}


def _parse_money(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    clean = re.sub(r"[$,\s]", "", str(val))
    try:
        return float(clean) if clean else None
    except ValueError:
        return None


def _parse_date(val) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt).date()
        except ValueError:
            continue
    return None


def _solicitation_to_project(sol: dict) -> Optional[ProjectIn]:
    sol_id = sol.get("id") or sol.get("solicitation_id")
    title = sol.get("title") or sol.get("name") or ""
    if not title:
        return None

    number = (
        sol.get("number") or sol.get("solicitation_number")
        or sol.get("reference_number") or str(sol_id or "")
    )
    close_raw = (
        sol.get("close_date") or sol.get("due_date") or sol.get("response_deadline")
        or sol.get("bid_due_date")
    )
    published_raw = sol.get("published_at") or sol.get("publish_date")
    estimate_raw = (
        sol.get("estimated_amount") or sol.get("budget") or sol.get("estimate")
    )
    description = sol.get("description") or sol.get("scope") or ""
    status_raw = str(sol.get("status") or "open").lower()
    is_archived = status_raw in ("closed", "awarded", "cancelled", "expired")

    detail_url = DETAIL_BASE + str(sol_id) if sol_id else PORTAL_URL

    return ProjectIn(
        external_id=str(number) if number else None,
        project_name=title,
        agency_owner=AGENCY,
        location_city=CITY,
        location_county=COUNTY,
        bid_due_date=_parse_date(close_raw),
        engineer_estimate=_parse_money(estimate_raw),
        description=description,
        trade_scope_raw=description or title,
        source_url=detail_url,
        status="awarded" if is_archived else "open",
        is_archived=is_archived,
    )


def _fetch_api(status: str = "open") -> list[ProjectIn]:
    projects: list[ProjectIn] = []
    page = 1
    while True:
        try:
            resp = httpx.get(
                f"{API_BASE}/solicitations",
                params={
                    "portal": PORTAL_SLUG,
                    "status": status,
                    "page": page,
                    "per_page": 50,
                    "sort": "close_date",
                    "order": "asc",
                },
                headers=HEADERS,
                timeout=15,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        if isinstance(data, list):
            items = data
            has_more = False
        elif isinstance(data, dict):
            items = (
                data.get("solicitations") or data.get("results")
                or data.get("data") or data.get("items") or []
            )
            meta = data.get("meta") or data.get("pagination") or {}
            total = meta.get("total_count") or meta.get("total") or len(items)
            has_more = (page * 50) < total
        else:
            break

        if not items:
            break

        for sol in items:
            p = _solicitation_to_project(sol)
            if p:
                projects.append(p)

        if has_more:
            page += 1
        else:
            break

    return projects


class VtaConnector(SourceConnector):
    name = "VTA Procurement"
    key = "vta"
    platform_type = "opengov"
    supports_current_bids = True
    supports_archives = False  # OpenGov API requires auth for historical data

    def fetch_current_projects(self) -> list[ProjectIn]:
        return _fetch_api(status="open")

    def fetch_archived_projects(self) -> list[ProjectIn]:
        seen: set[str] = set()
        result: list[ProjectIn] = []
        # OpenGov status values vary by portal version
        for status_val in ("closed", "awarded", "past", "archived", "complete"):
            batch = _fetch_api(status=status_val)
            for p in batch:
                key = p.external_id or p.project_name
                if key not in seen:
                    seen.add(key)
                    result.append(p)
            if result:
                break
        return result

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["live_api"] = f"{API_BASE}/solicitations"
        d["portal_url"] = PORTAL_URL
        try:
            projects = _fetch_api(status="open")
            if projects:
                d["status"] = "ok"
                d["projects_found"] = len(projects)
                d["sample"] = projects[0].project_name
            else:
                d["status"] = "api_empty_or_blocked"
                d["note"] = "API returned 0 results — may require auth or slug changed"
        except Exception as exc:
            d["status"] = "error"
            d["error"] = str(exc)
        return d
