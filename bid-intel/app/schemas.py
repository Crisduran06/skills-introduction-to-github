from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    key: str
    base_url: Optional[str] = None
    platform_type: str
    status: str
    supports_current_bids: bool
    supports_planholders: bool
    supports_bid_results: bool
    supports_awards: bool
    supports_archives: bool
    auth_required: bool
    scrape_allowed: bool
    last_checked_at: Optional[datetime] = None
    notes: Optional[str] = None
    archive_notes: Optional[str] = None


class ProjectIn(BaseModel):
    source_id: Optional[int] = None
    external_id: Optional[str] = None
    project_name: str
    agency_owner: Optional[str] = None
    location_city: Optional[str] = None
    location_county: Optional[str] = None
    bid_due_date: Optional[date] = None
    posted_date: Optional[date] = None
    prebid_date: Optional[date] = None
    estimate_value: Optional[float] = None
    engineer_estimate: Optional[float] = None
    description: Optional[str] = None
    trade_scope_raw: Optional[str] = None
    source_url: Optional[str] = None
    documents_url: Optional[str] = None
    planholders_url: Optional[str] = None
    results_url: Optional[str] = None
    award_url: Optional[str] = None
    archive_url: Optional[str] = None
    bid_type: Optional[str] = None
    project_type: Optional[str] = None
    construction_manager: Optional[str] = None
    architect: Optional[str] = None
    status: str = "open"
    is_archived: bool = False


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_id: Optional[int] = None
    external_id: Optional[str] = None
    project_name: str
    agency_owner: Optional[str] = None
    location_city: Optional[str] = None
    location_county: Optional[str] = None
    bid_due_date: Optional[date] = None
    posted_date: Optional[date] = None
    prebid_date: Optional[date] = None
    estimate_value: Optional[float] = None
    engineer_estimate: Optional[float] = None
    description: Optional[str] = None
    trade_scope_raw: Optional[str] = None
    relevance_score: Optional[int] = None
    relevance_reason: Optional[str] = None
    source_url: Optional[str] = None
    documents_url: Optional[str] = None
    planholders_url: Optional[str] = None
    results_url: Optional[str] = None
    award_url: Optional[str] = None
    archive_url: Optional[str] = None
    bid_type: Optional[str] = None
    project_type: Optional[str] = None
    construction_manager: Optional[str] = None
    architect: Optional[str] = None
    status: str
    is_archived: bool
    last_checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PlanholderIn(BaseModel):
    project_id: Optional[int] = None
    company_id: Optional[int] = None
    listed_as: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    date_added: Optional[date] = None
    source_url: Optional[str] = None
    confidence_score: Optional[float] = None
    notes: Optional[str] = None


class PlanholderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    company_id: Optional[int] = None
    listed_as: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    date_added: Optional[date] = None
    confidence_score: Optional[float] = None


class BidResultIn(BaseModel):
    project_id: Optional[int] = None
    company_id: Optional[int] = None
    bid_amount: Optional[float] = None
    is_low_bidder: bool = False
    is_awarded: bool = False
    bid_rank: Optional[int] = None
    result_date: Optional[date] = None
    responsive_status: Optional[str] = None
    notes: Optional[str] = None
    source_url: Optional[str] = None
    listed_as: Optional[str] = None


class BidResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    company_id: Optional[int] = None
    bid_amount: Optional[float] = None
    is_low_bidder: bool
    is_awarded: bool
    bid_rank: Optional[int] = None
    result_date: Optional[date] = None
    delta_from_low_amount: Optional[float] = None
    delta_from_low_percent: Optional[float] = None
    delta_from_previous_amount: Optional[float] = None
    delta_from_previous_percent: Optional[float] = None
    delta_from_engineer_estimate_amount: Optional[float] = None
    delta_from_engineer_estimate_percent: Optional[float] = None


class AddendumIn(BaseModel):
    project_id: Optional[int] = None
    addendum_number: Optional[int] = None
    title: Optional[str] = None
    posted_date: Optional[date] = None
    url: Optional[str] = None
    notes: Optional[str] = None


class ProjectBidAnalyticsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    project_id: int
    planholders_count: Optional[int] = None
    actual_bidders_count: Optional[int] = None
    non_bidding_planholders_count: Optional[int] = None
    bid_participation_rate: Optional[float] = None
    low_bid_amount: Optional[float] = None
    second_bid_amount: Optional[float] = None
    high_bid_amount: Optional[float] = None
    average_bid_amount: Optional[float] = None
    median_bid_amount: Optional[float] = None
    low_to_second_delta_amount: Optional[float] = None
    low_to_second_delta_percent: Optional[float] = None
    low_to_high_delta_amount: Optional[float] = None
    low_to_high_delta_percent: Optional[float] = None
    engineer_estimate: Optional[float] = None
    low_bid_vs_engineer_estimate_amount: Optional[float] = None
    low_bid_vs_engineer_estimate_percent: Optional[float] = None
    calculated_at: Optional[datetime] = None


class ManualImportIn(BaseModel):
    raw_text: str
    import_type: str = "auto"


class SubcontractorIn(BaseModel):
    project_id: Optional[int] = None
    company_id: Optional[int] = None
    bid_result_id: Optional[int] = None
    listed_as: Optional[str] = None
    trade_scope: Optional[str] = None
    role: str = "sub"
    source_url: Optional[str] = None
