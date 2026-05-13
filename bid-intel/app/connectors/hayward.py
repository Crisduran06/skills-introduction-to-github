"""Hayward Public Works connector — stub, live page structure TBD.

TODO: Confirm public page URL and HTML structure, then implement parser.
Live page: https://www.hayward-ca.gov/business/purchasing/bids-rfps
"""
from app.connectors.base import StubConnector

connector = StubConnector(
    name="Hayward Public Works",
    key="hayward",
    platform_type="public_page",
    notes="Live page structure needs confirmation. Implement parser when confirmed scrape-allowed.",
)
