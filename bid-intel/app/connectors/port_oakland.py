"""Port of Oakland connector — stub.

Port of Oakland procurement: https://www.portofoakland.com/business/doing-business/procurement/
TODO: Confirm public page structure and implement.
"""
from app.connectors.base import StubConnector

connector = StubConnector(
    name="Port of Oakland",
    key="port_oakland",
    platform_type="public_page",
    notes="Public procurement page — implement parser after confirming structure.",
)
