# routers/__init__.py
"""
FastAPI Routers for RealAlgo

This package contains FastAPI routers that replace Flask blueprints.
Each router maintains the same URL patterns and response formats as the
original Flask blueprints for frontend compatibility.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.7
"""

from routers.admin import admin_router
from routers.analyzer import analyzer_router
from routers.apikey import apikey_router
from routers.auth import auth_router
from routers.brlogin import brlogin_router
from routers.broker_credentials import broker_credentials_router
from routers.chartink import chartink_router
from routers.core import core_router
from routers.dashboard import dashboard_router
from routers.flow import flow_router
from routers.gc_json import gc_json_router
from routers.historify import historify_router
from routers.latency import latency_router
from routers.log import log_router
from routers.logging import logging_router
from routers.master_contract_status import master_contract_status_router
from routers.orders import orders_router
from routers.platforms import platforms_router
from routers.playground import playground_router
from routers.pnltracker import pnltracker_router
from routers.python_strategy import python_strategy_router
from routers.react_app import react_router
from routers.sandbox import sandbox_router
from routers.search import search_router
from routers.security import security_router
from routers.settings import settings_router
from routers.strategy import strategy_router
from routers.system_permissions import system_permissions_router
from routers.telegram import telegram_router
from routers.traffic import traffic_router
from routers.tv_json import tv_json_router

__all__ = [
    "admin_router",
    "analyzer_router",
    "apikey_router",
    "auth_router",
    "brlogin_router",
    "broker_credentials_router",
    "chartink_router",
    "core_router",
    "dashboard_router",
    "flow_router",
    "gc_json_router",
    "historify_router",
    "latency_router",
    "log_router",
    "logging_router",
    "master_contract_status_router",
    "orders_router",
    "platforms_router",
    "playground_router",
    "pnltracker_router",
    "python_strategy_router",
    "react_router",
    "sandbox_router",
    "search_router",
    "security_router",
    "settings_router",
    "strategy_router",
    "system_permissions_router",
    "telegram_router",
    "traffic_router",
    "tv_json_router",
]
