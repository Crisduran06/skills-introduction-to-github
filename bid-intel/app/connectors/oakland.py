"""Oakland Capital Contracts connector — stub.

TODO: Oakland uses a public procurement portal. Confirm URL and implement.
"""
from app.connectors.base import StubConnector

connector = StubConnector(
    name="Oakland Capital Contracts",
    key="oakland",
    platform_type="public_page",
    notes="Oakland uses PublicPurchase or similar portal. Confirm public access and implement.",
)
