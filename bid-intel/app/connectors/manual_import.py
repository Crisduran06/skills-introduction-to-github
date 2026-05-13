"""Manual import parser — extracts bid data from pasted raw text.

Supports: bid website copy-paste, bid alert email, planholder list,
bid tab / bid results, award notice, PDF text extract.
"""
from __future__ import annotations
import re
from datetime import datetime, date
from typing import Optional

from app.schemas import ProjectIn, PlanholderIn, BidResultIn


def _parse_money(s: str) -> Optional[float]:
    m = re.search(r"\$[\d,]+(?:\.\d+)?", s)
    if m:
        return float(re.sub(r"[$,\s]", "", m.group(0)))
    return None


def _parse_date(s: str) -> Optional[date]:
    patterns = [
        r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\w+ \d{1,2},? \d{4})\b",
    ]
    formats = ["%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            for fmt in formats:
                try:
                    return datetime.strptime(m.group(1), fmt).date()
                except ValueError:
                    continue
    return None


def parse_project_text(raw: str, import_type: str = "auto") -> dict:
    """Return dict with project, planholders, bid_results extracted from raw text."""
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    low_raw = raw.lower()

    project_name = ""
    agency = ""
    bid_due = None
    prebid = None
    estimate = None
    url = ""
    description_parts: list[str] = []
    planholders: list[PlanholderIn] = []
    bid_results: list[BidResultIn] = []

    for line in lines:
        low = line.lower()

        if any(k in low for k in ["project:", "project name:", "title:", "bid title:"]):
            project_name = re.sub(r"^[^:]+:\s*", "", line).strip()
        elif any(k in low for k in ["agency:", "owner:", "issued by:", "city of", "county of", "district"]):
            if ":" in line:
                agency = re.sub(r"^[^:]+:\s*", "", line).strip()
            elif not agency:
                agency = line
        elif any(k in low for k in ["bid due:", "bid date:", "bid deadline:", "due date:", "bids due:"]):
            bid_due = _parse_date(line)
        elif any(k in low for k in ["pre-bid:", "prebid:", "mandatory meeting:", "job walk:"]):
            prebid = _parse_date(line)
        elif any(k in low for k in ["estimate:", "engineer", "budget:", "amount:"]):
            val = _parse_money(line)
            if val:
                estimate = val
        elif line.startswith("http"):
            url = line
        else:
            description_parts.append(line)

    if not project_name and lines:
        project_name = lines[0][:300]

    # Detect bid results block
    result_pattern = re.compile(r"(.+?)\s*[-—]\s*(\$[\d,]+(?:\.\d+)?)(.*)", re.IGNORECASE)
    for line in lines:
        m = result_pattern.match(line)
        if m:
            company = m.group(1).strip()
            amount = _parse_money(m.group(2))
            rest = m.group(3).lower()
            bid_results.append(BidResultIn(
                listed_as=company,
                bid_amount=amount,
                is_low_bidder="low" in rest,
                is_awarded="award" in rest,
            ))

    # Detect planholder block
    if "plan holder" in low_raw or "planholder" in low_raw:
        for line in lines:
            if "@" in line or re.search(r"\d{3}[-.\s]\d{3}", line):
                planholders.append(PlanholderIn(listed_as=line[:200]))

    project = ProjectIn(
        project_name=project_name or "Unknown (manual import)",
        agency_owner=agency or None,
        bid_due_date=bid_due,
        prebid_date=prebid,
        estimate_value=estimate,
        source_url=url or None,
        description=" ".join(description_parts[:20]),
        trade_scope_raw=raw[:1000],
        status="open",
    )

    return {
        "project": project,
        "planholders": planholders,
        "bid_results": bid_results,
    }
