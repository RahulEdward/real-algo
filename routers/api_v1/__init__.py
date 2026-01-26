# routers/api_v1/__init__.py
"""
FastAPI REST API v1 Routers for RealAlgo

This package contains FastAPI routers that replace Flask-RESTX namespaces.
All endpoints are under /api/v1/ prefix and use API key authentication.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

# Import existing routers
from routers.api_v1.place_order import place_order_router
from routers.api_v1.place_smart_order import place_smart_order_router
from routers.api_v1.modify_order import modify_order_router
from routers.api_v1.cancel_order import cancel_order_router
from routers.api_v1.cancel_all_order import cancel_all_order_router
from routers.api_v1.close_position import close_position_router
from routers.api_v1.funds import funds_router
from routers.api_v1.orderbook import orderbook_router
from routers.api_v1.tradebook import tradebook_router
from routers.api_v1.positionbook import positionbook_router
from routers.api_v1.holdings import holdings_router
from routers.api_v1.orderstatus import orderstatus_router
from routers.api_v1.openposition import openposition_router
from routers.api_v1.quotes import quotes_router
from routers.api_v1.multiquotes import multiquotes_router
from routers.api_v1.depth import depth_router
from routers.api_v1.history import history_router
from routers.api_v1.intervals import intervals_router
from routers.api_v1.ticker import ticker_router
from routers.api_v1.symbol import symbol_router
from routers.api_v1.search import search_router
from routers.api_v1.expiry import expiry_router
from routers.api_v1.instruments import instruments_router
from routers.api_v1.option_chain import option_chain_router
from routers.api_v1.option_symbol import option_symbol_router
from routers.api_v1.option_greeks import option_greeks_router
from routers.api_v1.multi_option_greeks import multi_option_greeks_router
from routers.api_v1.options_order import options_order_router
from routers.api_v1.options_multiorder import options_multiorder_router
from routers.api_v1.synthetic_future import synthetic_future_router
from routers.api_v1.basket_order import basket_order_router
from routers.api_v1.split_order import split_order_router
from routers.api_v1.margin import margin_router
from routers.api_v1.analyzer import analyzer_router as api_analyzer_router
from routers.api_v1.ping import ping_router
from routers.api_v1.telegram_bot import telegram_bot_router
from routers.api_v1.chart_api import chart_api_router
from routers.api_v1.market_holidays import market_holidays_router
from routers.api_v1.market_timings import market_timings_router
from routers.api_v1.pnl_symbols import pnl_symbols_router

__all__ = [
    "place_order_router",
    "place_smart_order_router",
    "modify_order_router",
    "cancel_order_router",
    "cancel_all_order_router",
    "close_position_router",
    "funds_router",
    "orderbook_router",
    "tradebook_router",
    "positionbook_router",
    "holdings_router",
    "orderstatus_router",
    "openposition_router",
    "quotes_router",
    "multiquotes_router",
    "depth_router",
    "history_router",
    "intervals_router",
    "ticker_router",
    "symbol_router",
    "search_router",
    "expiry_router",
    "instruments_router",
    "option_chain_router",
    "option_symbol_router",
    "option_greeks_router",
    "multi_option_greeks_router",
    "options_order_router",
    "options_multiorder_router",
    "synthetic_future_router",
    "basket_order_router",
    "split_order_router",
    "margin_router",
    "api_analyzer_router",
    "ping_router",
    "telegram_bot_router",
    "chart_api_router",
    "market_holidays_router",
    "market_timings_router",
    "pnl_symbols_router",
]
