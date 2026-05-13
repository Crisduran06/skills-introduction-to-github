from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from app.schemas import ProjectIn, PlanholderIn, BidResultIn, AddendumIn
from app.models import Project


class SourceConnector(ABC):
    name: str = ""
    key: str = ""
    platform_type: str = "unknown"
    supports_current_bids: bool = False
    supports_planholders: bool = False
    supports_bid_results: bool = False
    supports_awards: bool = False
    supports_archives: bool = False

    def fetch_current_projects(self) -> list[ProjectIn]:
        return []

    def fetch_archived_projects(self) -> list[ProjectIn]:
        return []

    def fetch_planholders(self, project: Project) -> list[PlanholderIn]:
        return []

    def fetch_bid_results(self, project: Project) -> list[BidResultIn]:
        return []

    def fetch_award_info(self, project: Project) -> Optional[dict]:
        return None

    def fetch_addenda(self, project: Project) -> list[AddendumIn]:
        return []

    def debug_source(self) -> dict:
        return {
            "connector": self.__class__.__name__,
            "name": self.name,
            "key": self.key,
            "platform_type": self.platform_type,
            "supports_current_bids": self.supports_current_bids,
            "supports_planholders": self.supports_planholders,
            "supports_bid_results": self.supports_bid_results,
            "supports_awards": self.supports_awards,
            "supports_archives": self.supports_archives,
        }


class StubConnector(SourceConnector):
    """Placeholder for sources that require manual import or restricted access."""

    def __init__(self, name: str, key: str, platform_type: str = "unknown", notes: str = ""):
        self.name = name
        self.key = key
        self.platform_type = platform_type
        self._notes = notes

    def debug_source(self) -> dict:
        d = super().debug_source()
        d["status"] = "stub"
        d["notes"] = self._notes
        return d
