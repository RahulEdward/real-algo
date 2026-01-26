"""
Mapping utilities for Dhan broker integration.
Provides exchange code mappings between RealAlgo and Dhan formats.
"""

from typing import Dict

# Exchange code mappings
# RealAlgo exchange code -> Dhan exchange code
REALALGO_TO_DHAN_EXCHANGE = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FNO",
    "BFO": "BSE_FNO",
    "CDS": "NSE_CURRENCY",
    "BCD": "BSE_CURRENCY",
    "MCX": "MCX_COMM",
    "NSE_INDEX": "IDX_I",
    "BSE_INDEX": "IDX_I",
}

# Dhan exchange code -> RealAlgo exchange code
DHAN_TO_REALALGO_EXCHANGE = {v: k for k, v in REALALGO_TO_DHAN_EXCHANGE.items()}


def get_dhan_exchange(realalgo_exchange: str) -> str:
    """
    Convert RealAlgo exchange code to Dhan exchange code.

    Args:
        realalgo_exchange (str): Exchange code in RealAlgo format

    Returns:
        str: Exchange code in Dhan format
    """
    return REALALGO_TO_DHAN_EXCHANGE.get(realalgo_exchange, realalgo_exchange)


def get_realalgo_exchange(dhan_exchange: str) -> str:
    """
    Convert Dhan exchange code to RealAlgo exchange code.

    Args:
        dhan_exchange (str): Exchange code in Dhan format

    Returns:
        str: Exchange code in RealAlgo format
    """
    return DHAN_TO_REALALGO_EXCHANGE.get(dhan_exchange, dhan_exchange)
