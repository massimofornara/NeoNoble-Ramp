import pytest

from services.exchanges.connector_manager import get_connector_manager


@pytest.mark.asyncio
async def test_internal_symbol_detection():
    manager = get_connector_manager()

    assert manager._is_internal_symbol("NENO-EUR") is True
    assert manager._is_internal_symbol("TKNABC-USDT") is True
    assert manager._is_internal_symbol("BTC-USDT") is False
