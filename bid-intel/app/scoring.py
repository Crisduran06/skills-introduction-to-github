from __future__ import annotations
import re

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
