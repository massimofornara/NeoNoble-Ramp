import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from services.liquidity.routing_service import MarketRoutingService


@pytest.mark.asyncio
async def test_initialize_routing():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.test_neonoble_routing_1

    service = MarketRoutingService(db)
    await service.initialize()

    assert service._initialized is True


@pytest.mark.asyncio
async def test_get_conversion_path():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.test_neonoble_routing_2

    service = MarketRoutingService(db)
    await service.initialize()

    path = await service.get_conversion_path("NENO", "EUR", 10)

    assert path is not None
    assert path.destination_currency == "EUR"


@pytest.mark.asyncio
async def test_execute_conversion():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.test_neonoble_routing_3

    service = MarketRoutingService(db)
    await service.initialize()

    event = await service.execute_conversion(
        source_currency="NENO",
        source_amount=5,
        destination_currency="EUR"
    )

    assert event is not None
    assert event.status is not None
