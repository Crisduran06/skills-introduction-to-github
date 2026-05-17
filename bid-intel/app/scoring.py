from __future__ import annotations
import re
from typing import Optional

HIGH_KEYWORDS = [
    "electrical", "low voltage", "fire alarm", "fire protection",
    "security", "cctv", "access control", "ev charging", "electric vehicle",
    "switchgear", "transformer", "generator", "emergency power",
    "lighting", "led", "data", "fiber", "communications", "comm",
    "power distribution", "panelboard", "panel board", "mcc",
    "motor control", "controls", "scada", "instrumentation",
    "uninterruptible power", "ups", "automatic transfer switch", "ats",
    "emergency lighting", "exit signs", "conduit", "wire", "wiring",
    "photovoltaic", "solar", "battery storage", "energy storage",
    "substation", "medium voltage", "high voltage",
]

MEDIUM_KEYWORDS = [
    "building renovation", "mep", "mechanical electrical plumbing",
    "facility upgrade", "facility improvement", "facility modernization",
    "pump station", "wastewater", "water treatment", "treatment plant",
    "station improvement", "airport", "school modernization",
    "tenant improvement", "civic", "community center",
    "library", "park facility", "recreation center",
    "fire station", "police station", "public works",
    "infrastructure", "capital improvement",
    "hvac", "mechanical", "plumbing",
]

LOW_KEYWORDS = [
    "paving", "landscaping", "striping", "pavement marking",
    "roofing", "janitorial", "custodial", "tree trimming",
    "painting only", "fencing only", "sidewalk", "curb and gutter",
    "trail", "park irrigation", "playground",
]


def _normalize(text: str) -> str:
    return text.lower()


def infer_bid_type(text: str) -> Optional[str]:
    t = text.lower()
    if any(x in t for x in ["lease-leaseback", "lease leaseback", " llb ", "(llb)", "llb "]):
        return "lease_leaseback"
    if any(x in t for x in ["cmar", "cm at risk", "cm@risk", "construction manager at risk"]):
        return "cmar"
    if any(x in t for x in ["design-build", "design build", "design/build"]):
        return "design_build"
    if re.search(r'\brfq\b', t) or "request for qualifications" in t:
        return "rfq"
    if re.search(r'\brfp\b', t) or "request for proposal" in t:
        return "rfp"
    if re.search(r'\bifb\b', t) or "invitation for bid" in t or "invitation to bid" in t:
        return "ifb"
    return None


def infer_project_type(text: str) -> Optional[str]:
    t = text.lower()
    if any(x in t for x in ["school", "unified", "elementary", "high school", "campus", "classroom",
                             "k-12", "district", "education", "academic", "student", "portable",
                             "gymnasium", "cafeteria", "library modernization"]):
        return "k12"
    if any(x in t for x in ["water", "sewer", "wastewater", "pump station", "water treatment",
                             "pipeline", "storm drain", "drainage", "reservoir", "potable"]):
        return "water_utility"
    if any(x in t for x in ["bart ", "light rail", "transit center", "bus rapid", " brt ",
                             "rail station", "caltrain"]):
        return "transit"
    if any(x in t for x in ["airport", "terminal", "sfo", "airfield", "runway", "taxiway"]):
        return "airport"
    if any(x in t for x in ["port of", " wharf", "marine facility", " pier ", "berth", "cargo"]):
        return "port"
    if any(x in t for x in ["park improvement", "recreation center", "community center",
                             "trail improvement", "open space", "sports complex"]):
        return "parks"
    return "municipal"


def score_project(project_name: str, description: str = "", trade_scope: str = "") -> tuple[int, str]:
    combined = _normalize(f"{project_name} {description} {trade_scope}")
    reasons: list[str] = []

    high_hits = [kw for kw in HIGH_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', combined)]
    medium_hits = [kw for kw in MEDIUM_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', combined)]
    low_hits = [kw for kw in LOW_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', combined)]

    if high_hits:
        score = 5
        reasons.append(f"High-relevance scope: {', '.join(high_hits[:5])}")
    elif medium_hits and not low_hits:
        score = 4
        reasons.append(f"MEP/facility project likely including electrical: {', '.join(medium_hits[:3])}")
    elif medium_hits:
        score = 3
        reasons.append(f"Mixed signals — may include electrical: {', '.join(medium_hits[:3])}")
    elif low_hits and not medium_hits:
        score = 1
        reasons.append(f"Likely not relevant: {', '.join(low_hits[:3])}")
    else:
        score = 2
        reasons.append("Unclear scope — manual plan review recommended")

    reason = "; ".join(reasons) if reasons else "No keyword matches found"
    return score, reason
