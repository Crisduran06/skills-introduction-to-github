from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
import enum


class PlatformType(str, enum.Enum):
    public_page = "public_page"
    planetbids = "planetbids"
    bidnet = "bidnet"
    pdf_bulletin = "pdf_bulletin"
    manual_import = "manual_import"
    email_alert = "email_alert"
    api = "api"
    unknown = "unknown"


class SourceStatus(str, enum.Enum):
    live = "live"
    fixture_only = "fixture_only"
    stub = "stub"
    manual_only = "manual_only"
    disabled = "disabled"


class ProjectStatus(str, enum.Enum):
    open = "open"
    addenda = "addenda"
    bid_opened = "bid_opened"
    awarded = "awarded"
    canceled = "canceled"
    archived = "archived"
    unknown = "unknown"


class CompanyType(str, enum.Enum):
    gc = "gc"
    electrical_sub = "electrical_sub"
    low_voltage_sub = "low_voltage_sub"
    supplier = "supplier"
    agency = "agency"
    unknown = "unknown"


class DecisionChoice(str, enum.Enum):
    review = "review"
    pursue = "pursue"
    pass_ = "pass"
    submitted = "submitted"
    tracking_results = "tracking_results"
    won_by_other = "won_by_other"
    awarded_to_us = "awarded_to_us"
    closed = "closed"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    source_type: Mapped[Optional[str]] = mapped_column(String(100))
    platform_type: Mapped[str] = mapped_column(String(50), default="unknown")
    auth_required: Mapped[bool] = mapped_column(Boolean, default=False)
    scrape_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(50), default="stub")
    supports_current_bids: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_planholders: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_bid_results: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_awards: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_archives: Mapped[bool] = mapped_column(Boolean, default=False)
    archive_notes: Mapped[Optional[str]] = mapped_column(Text)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    projects: Mapped[list[Project]] = relationship("Project", back_populates="source")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sources.id"))
    external_id: Mapped[Optional[str]] = mapped_column(String(255))
    project_name: Mapped[str] = mapped_column(String(500))
    agency_owner: Mapped[Optional[str]] = mapped_column(String(255))
    location_city: Mapped[Optional[str]] = mapped_column(String(255))
    location_county: Mapped[Optional[str]] = mapped_column(String(255))
    bid_due_date: Mapped[Optional[date]] = mapped_column(Date)
    posted_date: Mapped[Optional[date]] = mapped_column(Date)
    prebid_date: Mapped[Optional[date]] = mapped_column(Date)
    estimate_value: Mapped[Optional[float]] = mapped_column(Float)
    engineer_estimate: Mapped[Optional[float]] = mapped_column(Float)
    description: Mapped[Optional[str]] = mapped_column(Text)
    trade_scope_raw: Mapped[Optional[str]] = mapped_column(Text)
    relevance_score: Mapped[Optional[int]] = mapped_column(Integer)
    relevance_reason: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    documents_url: Mapped[Optional[str]] = mapped_column(String(1000))
    planholders_url: Mapped[Optional[str]] = mapped_column(String(1000))
    results_url: Mapped[Optional[str]] = mapped_column(String(1000))
    award_url: Mapped[Optional[str]] = mapped_column(String(1000))
    archive_url: Mapped[Optional[str]] = mapped_column(String(1000))
    bid_type: Mapped[Optional[str]] = mapped_column(String(50))   # ifb, rfq, rfp, lease_leaseback, cmar, design_build
    project_type: Mapped[Optional[str]] = mapped_column(String(100))  # k12, water_utility, transit, airport, port, municipal, parks
    construction_manager: Mapped[Optional[str]] = mapped_column(String(255))
    architect: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source: Mapped[Optional[Source]] = relationship("Source", back_populates="projects")
    planholders: Mapped[list[Planholder]] = relationship("Planholder", back_populates="project", cascade="all, delete-orphan")
    bid_results: Mapped[list[BidResult]] = relationship("BidResult", back_populates="project", cascade="all, delete-orphan")
    addenda: Mapped[list[Addendum]] = relationship("Addendum", back_populates="project", cascade="all, delete-orphan")
    notes: Mapped[list[ProjectNote]] = relationship("ProjectNote", back_populates="project", cascade="all, delete-orphan")
    decision_status: Mapped[Optional[DecisionStatus]] = relationship("DecisionStatus", back_populates="project", uselist=False, cascade="all, delete-orphan")
    bid_analytics: Mapped[Optional[ProjectBidAnalytics]] = relationship("ProjectBidAnalytics", back_populates="project", uselist=False, cascade="all, delete-orphan")
    company_participations: Mapped[list[CompanyProjectParticipation]] = relationship("CompanyProjectParticipation", back_populates="project", cascade="all, delete-orphan")
    subcontractors: Mapped[list["ProjectSubcontractor"]] = relationship("ProjectSubcontractor", back_populates="project", cascade="all, delete-orphan")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    address: Mapped[Optional[str]] = mapped_column(Text)
    company_type: Mapped[str] = mapped_column(String(50), default="unknown")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    planholders: Mapped[list[Planholder]] = relationship("Planholder", back_populates="company")
    bid_results: Mapped[list[BidResult]] = relationship("BidResult", back_populates="company")
    participations: Mapped[list[CompanyProjectParticipation]] = relationship("CompanyProjectParticipation", back_populates="company")
    subcontractor_entries: Mapped[list["ProjectSubcontractor"]] = relationship("ProjectSubcontractor", back_populates="company")


class Planholder(Base):
    __tablename__ = "planholders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.id"))
    listed_as: Mapped[Optional[str]] = mapped_column(String(500))
    contact_name: Mapped[Optional[str]] = mapped_column(String(255))
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50))
    date_added: Mapped[Optional[date]] = mapped_column(Date)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Project] = relationship("Project", back_populates="planholders")
    company: Mapped[Optional[Company]] = relationship("Company", back_populates="planholders")


class BidResult(Base):
    __tablename__ = "bid_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.id"))
    bid_amount: Mapped[Optional[float]] = mapped_column(Float)
    is_low_bidder: Mapped[bool] = mapped_column(Boolean, default=False)
    is_awarded: Mapped[bool] = mapped_column(Boolean, default=False)
    bid_rank: Mapped[Optional[int]] = mapped_column(Integer)
    result_date: Mapped[Optional[date]] = mapped_column(Date)
    responsive_status: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    delta_from_low_amount: Mapped[Optional[float]] = mapped_column(Float)
    delta_from_low_percent: Mapped[Optional[float]] = mapped_column(Float)
    delta_from_previous_amount: Mapped[Optional[float]] = mapped_column(Float)
    delta_from_previous_percent: Mapped[Optional[float]] = mapped_column(Float)
    delta_from_engineer_estimate_amount: Mapped[Optional[float]] = mapped_column(Float)
    delta_from_engineer_estimate_percent: Mapped[Optional[float]] = mapped_column(Float)

    project: Mapped[Project] = relationship("Project", back_populates="bid_results")
    company: Mapped[Optional[Company]] = relationship("Company", back_populates="bid_results")


class ProjectBidAnalytics(Base):
    __tablename__ = "project_bid_analytics"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), primary_key=True)
    planholders_count: Mapped[Optional[int]] = mapped_column(Integer)
    actual_bidders_count: Mapped[Optional[int]] = mapped_column(Integer)
    non_bidding_planholders_count: Mapped[Optional[int]] = mapped_column(Integer)
    bid_participation_rate: Mapped[Optional[float]] = mapped_column(Float)
    low_bid_amount: Mapped[Optional[float]] = mapped_column(Float)
    second_bid_amount: Mapped[Optional[float]] = mapped_column(Float)
    high_bid_amount: Mapped[Optional[float]] = mapped_column(Float)
    average_bid_amount: Mapped[Optional[float]] = mapped_column(Float)
    median_bid_amount: Mapped[Optional[float]] = mapped_column(Float)
    low_to_second_delta_amount: Mapped[Optional[float]] = mapped_column(Float)
    low_to_second_delta_percent: Mapped[Optional[float]] = mapped_column(Float)
    low_to_high_delta_amount: Mapped[Optional[float]] = mapped_column(Float)
    low_to_high_delta_percent: Mapped[Optional[float]] = mapped_column(Float)
    engineer_estimate: Mapped[Optional[float]] = mapped_column(Float)
    low_bid_vs_engineer_estimate_amount: Mapped[Optional[float]] = mapped_column(Float)
    low_bid_vs_engineer_estimate_percent: Mapped[Optional[float]] = mapped_column(Float)
    calculated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship("Project", back_populates="bid_analytics")


class CompanyProjectParticipation(Base):
    __tablename__ = "company_project_participation"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), primary_key=True)
    was_planholder: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_bid: Mapped[bool] = mapped_column(Boolean, default=False)
    was_low_bidder: Mapped[bool] = mapped_column(Boolean, default=False)
    was_awarded: Mapped[bool] = mapped_column(Boolean, default=False)
    bid_amount: Mapped[Optional[float]] = mapped_column(Float)
    bid_rank: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Project] = relationship("Project", back_populates="company_participations")
    company: Mapped[Company] = relationship("Company", back_populates="participations")


class Addendum(Base):
    __tablename__ = "addenda"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    addendum_number: Mapped[Optional[int]] = mapped_column(Integer)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    posted_date: Mapped[Optional[date]] = mapped_column(Date)
    url: Mapped[Optional[str]] = mapped_column(String(1000))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Project] = relationship("Project", back_populates="addenda")


class ProjectNote(Base):
    __tablename__ = "project_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(255))

    project: Mapped[Project] = relationship("Project", back_populates="notes")


class DecisionStatus(Base):
    __tablename__ = "decision_status"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), primary_key=True)
    decision: Mapped[str] = mapped_column(String(50), default="review")
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255))
    follow_up_date: Mapped[Optional[date]] = mapped_column(Date)
    reason: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Project] = relationship("Project", back_populates="decision_status")


class ProjectSubcontractor(Base):
    __tablename__ = "project_subcontractors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.id"))
    bid_result_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("bid_results.id"))
    listed_as: Mapped[Optional[str]] = mapped_column(String(500))
    trade_scope: Mapped[Optional[str]] = mapped_column(String(255))  # "Electrical", "Plumbing", etc.
    role: Mapped[str] = mapped_column(String(50), default="sub")
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship("Project", back_populates="subcontractors")
    company: Mapped[Optional[Company]] = relationship("Company", back_populates="subcontractor_entries")
