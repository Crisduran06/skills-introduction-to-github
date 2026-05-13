"""Valley Water PlanetBids connector — manual/API required.

Valley Water uses PlanetBids portal which requires login to view planholder lists.
Current bid summaries may be available on the public listing page.
TODO: Check if public bid list page is accessible without login.
"""
from app.connectors.base import StubConnector

connector = StubConnector(
    name="Valley Water PlanetBids",
    key="valley_water",
    platform_type="planetbids",
    notes="PlanetBids portal — planholder/result detail requires login. Manual import supported.",
)
