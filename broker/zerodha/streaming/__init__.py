"""
Zerodha WebSocket streaming module for RealAlgo.

This module provides WebSocket integration with Zerodha's market data streaming API,
following the RealAlgo WebSocket proxy architecture.
"""

from .zerodha_adapter import ZerodhaWebSocketAdapter

__all__ = ["ZerodhaWebSocketAdapter"]
