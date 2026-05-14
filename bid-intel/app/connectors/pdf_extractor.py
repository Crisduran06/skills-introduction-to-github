"""PDF scraper for bid tabulations and award notice PDFs.

Finds PDF links on agency web pages, downloads them, extracts text with
pdfplumber, and parses out project info + bidder amounts.
"""
from __future__ import annotations
import io
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas import ProjectIn, BidResultIn

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BidIntel/1.0; +https://github.com)"}
MAX_PDF_BYTES = 8 * 1024 * 1024  # skip PDFs over 8 MB

MONEY_RE = re.compile(r'\$\s*[\d,]+(?:\.\d{2})?')
CONTRACT_RE = re.compile(
    r'\b(?:Contract\s*No\.?|Contract\s*#|Spec\.?\s*No\.?|C/N|Project\s*No\.?)\s*:?\s*'
    r'([A-Z0-9][\w\-]{2,25})',
    re.I,
)
DATE_FMTS = (
    "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%B %d, %Y",
    "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%Y-%m-%d",
)


# ---------------------------------------------------------------------------
# Link finder
# ---------------------------------------------------------------------------

def find_pdf_links(page_url: str) -> list[str]:
    """Fetch page_url and return absolute URLs of all linked PDFs."""
    try:
        resp = httpx.get(page_url, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    parsed = urlparse(page_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    soup = BeautifulSoup(resp.text, "lxml")
    seen: set[str] = set()
    pdfs: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.lower().endswith(".pdf"):
            continue
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = base + href
        else:
            url = base + "/" + href.lstrip("/")
        if url not in seen:
            seen.add(url)
            pdfs.append(url)
    return pdfs


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_url: str) -> str:
    """Download pdf_url and return concatenated page text, or '' on failure."""
    try:
        import pdfplumber
    except ImportError:
        return ""
    try:
        resp = httpx.get(pdf_url, headers=HEADERS, timeout=25, follow_redirects=True)
        resp.raise_for_status()
        if len(resp.content) > MAX_PDF_BYTES:
            return ""
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            for page in pdf.pages[:12]:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n".join(pages)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _money(s: str) -> Optional[float]:
    clean = re.sub(r"[$,\s]", "", s)
    try:
        return float(clean) if clean else None
    except ValueError:
        return None


def _parse_date(s: str) -> Optional[date]:
    s = s.strip()
    for fmt in DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Award / bid-tab PDF parser
# ---------------------------------------------------------------------------

_SKIP_TITLE_STARTS = re.compile(
    r"^(bid\s*tab|notice|award|page\s*\d|date|subject|re:|to:|from:|project\s*no|"
    r"contract\s*no|spec\s*no|bart|sfpuc|ebmud|city\s*of|county\s*of)",
    re.I,
)
_HEADER_COMPANY = re.compile(
    r"^(bidder|contractor|company|name|firm|vendor|subcontractor)s?\b", re.I
)


def parse_award_pdf(
    text: str,
    pdf_url: str,
    agency: str,
    city: str,
    county: str,
) -> tuple[Optional[ProjectIn], list[BidResultIn]]:
    """Parse a bid tabulation or award-notice PDF into project + bid results."""
    if not text or len(text) < 60:
        return None, []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # --- Contract number ---
    contract_num = ""
    for line in lines[:40]:
        m = CONTRACT_RE.search(line)
        if m:
            contract_num = m.group(1)
            break

    # --- Project title ---
    # First substantial line that doesn't look like a header/label
    title = ""
    for line in lines[:30]:
        if len(line) < 12 or _SKIP_TITLE_STARTS.match(line):
            # Still try to extract value after colon ("Project: XYZ")
            if ":" in line:
                candidate = line.split(":", 1)[-1].strip()
                if len(candidate) > 12 and not re.match(r'^[\$\d]', candidate):
                    title = candidate
                    break
            continue
        if re.match(r'^[\$\d]', line):
            continue
        title = line
        break

    if not title:
        return None, []

    # --- Engineer's estimate ---
    estimate: Optional[float] = None
    for line in lines:
        if re.search(r"engineer.{0,12}estimate|owner.{0,8}estimate|\bee\b", line, re.I):
            amounts = MONEY_RE.findall(line)
            if amounts:
                estimate = _money(amounts[-1])
                break

    # --- Bid / opening date ---
    bid_date: Optional[date] = None
    for line in lines[:20]:
        if re.search(r"bid\s*(due|date|open|received|tab)|open(ing)?\s*date", line, re.I):
            m = re.search(
                r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s*\d{4}',
                line, re.I,
            )
            if m:
                bid_date = _parse_date(m.group(0))
                break

    # --- Bidder table ---
    # Lines that contain a $ amount and a preceding company-name-like string
    amounts_found: list[tuple[str, float]] = []
    in_bid_section = False
    for line in lines:
        if re.search(r"list\s*of\s*bidder|bid\s*tab|bidder\s+bid\s+amount", line, re.I):
            in_bid_section = True
            continue

        amounts = MONEY_RE.findall(line)
        if not amounts:
            continue

        # Once we see $-amounts, assume we're in the bid section
        in_bid_section = True

        # Strip amounts from line to get company name
        company = MONEY_RE.sub("", line).strip().strip(".-–—").strip()
        company = re.sub(r'^\d+[\.\)\s]+', '', company).strip()  # remove "1. " rank prefix

        if len(company) < 3 or len(company) > 90:
            continue
        if _HEADER_COMPANY.match(company):
            continue

        amt = _money(amounts[0])
        if amt and amt > 5_000:  # filter out unit prices / small numbers
            amounts_found.append((company, amt))

    bid_results: list[BidResultIn] = []
    if amounts_found:
        min_amt = min(a for _, a in amounts_found)
        for rank, (company, amt) in enumerate(
            sorted(amounts_found, key=lambda x: x[1]), start=1
        ):
            is_low = abs(amt - min_amt) < 1.0
            bid_results.append(BidResultIn(
                listed_as=company,
                bid_amount=amt,
                bid_rank=rank,
                is_low_bidder=is_low,
                is_awarded=is_low,
                result_date=bid_date,
                source_url=pdf_url,
            ))

    project = ProjectIn(
        external_id=contract_num or None,
        project_name=title,
        agency_owner=agency,
        location_city=city,
        location_county=county,
        bid_due_date=bid_date,
        engineer_estimate=estimate,
        trade_scope_raw=title,
        source_url=pdf_url,
        status="awarded" if bid_results else "bid_opened",
        is_archived=True,
    )
    return project, bid_results


# ---------------------------------------------------------------------------
# High-level helper: scrape a page's PDFs and return all parsed results
# ---------------------------------------------------------------------------

def scrape_pdfs_from_page(
    page_url: str,
    agency: str,
    city: str,
    county: str,
    max_pdfs: int = 30,
) -> list[tuple[ProjectIn, list[BidResultIn]]]:
    """Find PDF links on page_url, parse each one, return (project, results) pairs."""
    pdf_urls = find_pdf_links(page_url)
    results: list[tuple[ProjectIn, list[BidResultIn]]] = []
    seen_titles: set[str] = set()
    for pdf_url in pdf_urls[:max_pdfs]:
        text = extract_pdf_text(pdf_url)
        project, bid_results = parse_award_pdf(text, pdf_url, agency, city, county)
        if project and project.project_name not in seen_titles:
            seen_titles.add(project.project_name)
            results.append((project, bid_results))
    return results
