"""SFPUC / SF Public Works connector — stub.

SF uses multiple procurement systems. SFPUC bids are public.
TODO: Implement parser for https://sfwater.org/index.aspx?page=124
SF Public Works: https://sfpublicworks.org/doing-business
"""
from app.connectors.base import StubConnector

connector = StubConnector(
    name="SFPUC / SF Bids",
    key="sfpuc",
    platform_type="public_page",
    notes="SFPUC public bid page — implement parser. SF Public Works uses separate system.",
)
