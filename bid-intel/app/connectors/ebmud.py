"""EBMUD Construction Bids connector — stub.

EBMUD publishes bids publicly at https://www.ebmud.com/about-ebmud/business/bids-rfps/
TODO: Confirm HTML structure and implement parser.
"""
from app.connectors.base import StubConnector

connector = StubConnector(
    name="EBMUD Construction Bids",
    key="ebmud",
    platform_type="public_page",
    notes="Public page — implement parser after confirming HTML structure.",
)
