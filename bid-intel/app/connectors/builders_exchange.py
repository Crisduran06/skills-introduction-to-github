"""Bay Area Builders Exchange / CalBX / BXSCCO connector — stub.

BXSCCO publishes a weekly PDF bid bulletin. CalBX requires membership for full access.
Only public/free portions should be accessed.
TODO: Determine if weekly bulletin PDF is publicly downloadable.
"""
from app.connectors.base import StubConnector

connector = StubConnector(
    name="Bay Area Builders Exchange / CalBX",
    key="builders_exchange",
    platform_type="pdf_bulletin",
    notes="Weekly PDF bulletin — check public access. Membership may be required for full listings.",
)
