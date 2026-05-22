"""
DEX Integration Package - C-SAFE Real Market Conversion.

Provides real on-chain DEX swap execution for the off-ramp flow:
- 1inch Aggregator (primary)
- PancakeSwap V3 (fallback)
- Progressive batch execution (TWAP-like)
- Safety controls and audit logging
"""

from .dex_service import (
    DEXService,
    get_dex_service,
    set_dex_service
)

from .batch_executor import (
    BatchExecutor,
    BatchConfig,
    BatchResult
)

__all__ = [
    'DEXService',
    'get_dex_service',
    'set_dex_service',
    'BatchExecutor',
    'BatchConfig',
    'BatchResult'
]
