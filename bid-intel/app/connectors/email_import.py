"""Email import connector — parses forwarded bid alert emails.

Supports manual paste of bid alert email content into the manual import form.
No automated email access is implemented — this is a manual import workflow.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

from app.schemas import ProjectIn


def parse_email_text(raw_text: str) -> Optional[ProjectIn]:
    """Extract project info from a pasted bid alert email body."""
    lines = raw_text.strip().splitlines()
    project_name = ""
    agency = ""
    bid_due = None
    estimate = None
    url = ""
    description_lines: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        low = line.lower()

        if not project_name and len(line) > 5 and not any(k in low for k in ["from:", "to:", "subject:", "date:"]):
            if any(k in low for k in ["project", "bid", "rfp", "rfq", "contract"]):
                project_name = line

        if "due:" in low or "deadline:" in low or "bid date:" in low:
            m = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", line)
            if m:
                for fmt in ("%m/%d/%Y", "%m/%d/%y"):
                    try:
                        bid_due = datetime.strptime(m.group(0), fmt).date()
                        break
                    except ValueError:
                        continue

        if any(k in low for k in ["estimate:", "engineer's estimate:", "value:"]):
            m = re.search(r"\$[\d,]+", line)
            if m:
                estimate = float(re.sub(r"[^\d.]", "", m.group(0)))

        if any(k in low for k in ["agency:", "owner:", "issued by:", "from:"]):
            agency = re.sub(r"^[^:]+:\s*", "", line).strip()

        if line.startswith("http"):
            url = line

        description_lines.append(line)

    if not project_name and lines:
        project_name = lines[0][:200]

    return ProjectIn(
        project_name=project_name or "Unknown (email import)",
        agency_owner=agency or None,
        bid_due_date=bid_due,
        estimate_value=estimate,
        source_url=url or None,
        description=" ".join(description_lines[:10]),
        trade_scope_raw=raw_text[:500],
        status="open",
    )
