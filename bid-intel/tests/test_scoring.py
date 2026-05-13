import pytest
from app.scoring import score_project


def test_high_score_electrical():
    score, reason = score_project("City Hall Electrical Service Upgrade", "Replacement of 480V switchgear and panelboard")
    assert score == 5
    assert "electrical" in reason.lower() or "switchgear" in reason.lower() or "panelboard" in reason.lower()


def test_high_score_fire_alarm():
    score, reason = score_project("Community Center Fire Alarm Replacement", "NFPA 72 addressable system")
    assert score == 5


def test_high_score_ev_charging():
    score, reason = score_project("EV Charging Infrastructure Project", "Level 2 and DC fast charging stations")
    assert score == 5


def test_high_score_scada():
    score, reason = score_project("Water Treatment Plant SCADA Controls Upgrade", "PLC-based control system")
    assert score == 5


def test_high_score_generator():
    score, reason = score_project("Emergency Generator Installation", "standby generator and automatic transfer switch")
    assert score == 5


def test_medium_score_facility():
    score, reason = score_project("Senior Center Modernization", "facility upgrade building renovation")
    assert score >= 3


def test_medium_score_pump_station():
    score, reason = score_project("Pump Station Improvements", "pump station wastewater upgrades")
    assert score >= 3


def test_low_score_paving():
    score, reason = score_project("Street Paving Project", "asphalt paving striping landscaping")
    assert score <= 2


def test_low_score_landscaping():
    score, reason = score_project("Park Landscaping", "tree trimming irrigation trail")
    assert score <= 2


def test_returns_reason_string():
    score, reason = score_project("LED Lighting Retrofit", "")
    assert isinstance(reason, str)
    assert len(reason) > 0


def test_score_range():
    for name in ["electrical panel", "mep renovation", "park paving", "communications fiber"]:
        score, _ = score_project(name)
        assert 1 <= score <= 5
