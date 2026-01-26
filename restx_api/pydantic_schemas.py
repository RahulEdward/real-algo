"""
Pydantic Models for RealAlgo REST API

This module provides Pydantic models that replace Marshmallow schemas
for FastAPI request/response validation.

Requirements: 5.2
"""

import re
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================
# Enums for validation
# ============================================================

class ActionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    buy = "buy"
    sell = "sell"


class PriceType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class ProductType(str, Enum):
    MIS = "MIS"
    NRML = "NRML"
    CNC = "CNC"


class OptionsProductType(str, Enum):
    MIS = "MIS"
    NRML = "NRML"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"
    ce = "ce"
    pe = "pe"


class ExchangeType(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    CDS = "CDS"
    MCX = "MCX"
    NSE_INDEX = "NSE_INDEX"
    BSE_INDEX = "BSE_INDEX"
    BCD = "BCD"


class DerivativeExchange(str, Enum):
    NFO = "NFO"
    BFO = "BFO"
    MCX = "MCX"
    CDS = "CDS"


class InstrumentType(str, Enum):
    futures = "futures"
    options = "options"


class IntervalType(str, Enum):
    # Seconds
    s1 = "1s"
    s5 = "5s"
    s10 = "10s"
    s15 = "15s"
    s30 = "30s"
    s45 = "45s"
    # Minutes
    m1 = "1m"
    m2 = "2m"
    m3 = "3m"
    m5 = "5m"
    m10 = "10m"
    m15 = "15m"
    m20 = "20m"
    m30 = "30m"
    # Hours
    h1 = "1h"
    h2 = "2h"
    h3 = "3h"
    h4 = "4h"
    # Daily, Weekly, Monthly, Quarterly, Yearly
    D = "D"
    W = "W"
    M = "M"
    Q = "Q"
    Y = "Y"


class TickerIntervalType(str, Enum):
    m1 = "1m"
    m5 = "5m"
    m15 = "15m"
    m30 = "30m"
    h1 = "1h"
    h4 = "4h"
    D = "D"
    W = "W"
    M = "M"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class DataSource(str, Enum):
    api = "api"
    db = "db"


class OutputFormat(str, Enum):
    json = "json"
    csv = "csv"


# ============================================================
# Base Models
# ============================================================

class APIKeyModel(BaseModel):
    """Base model with API key authentication"""
    apikey: str = Field(..., min_length=1, description="API key for authentication")


class StrategyModel(APIKeyModel):
    """Base model with API key and strategy"""
    strategy: str = Field(..., min_length=1, description="Strategy name")


# ============================================================
# Order Schemas
# ============================================================

class PlaceOrderRequest(StrategyModel):
    """Request model for placing an order"""
    exchange: str = Field(..., description="Exchange (NSE, BSE, NFO, etc.)")
    symbol: str = Field(..., description="Trading symbol")
    action: ActionType = Field(..., description="Order action (BUY/SELL)")
    quantity: int = Field(..., ge=1, description="Order quantity (must be positive)")
    pricetype: PriceType = Field(default=PriceType.MARKET, description="Price type")
    product: ProductType = Field(default=ProductType.MIS, description="Product type")
    price: float = Field(default=0.0, ge=0, description="Order price (for LIMIT orders)")
    trigger_price: float = Field(default=0.0, ge=0, description="Trigger price (for SL orders)")
    disclosed_quantity: int = Field(default=0, ge=0, description="Disclosed quantity")
    underlying_ltp: Optional[float] = Field(default=None, description="Underlying LTP for options")


class SmartOrderRequest(StrategyModel):
    """Request model for placing a smart order"""
    exchange: str = Field(..., description="Exchange")
    symbol: str = Field(..., description="Trading symbol")
    action: ActionType = Field(..., description="Order action")
    quantity: int = Field(..., ge=0, description="Order quantity")
    position_size: int = Field(..., description="Current position size")
    pricetype: PriceType = Field(default=PriceType.MARKET)
    product: ProductType = Field(default=ProductType.MIS)
    price: float = Field(default=0.0, ge=0)
    trigger_price: float = Field(default=0.0, ge=0)
    disclosed_quantity: int = Field(default=0, ge=0)


class ModifyOrderRequest(StrategyModel):
    """Request model for modifying an order"""
    exchange: str = Field(...)
    symbol: str = Field(...)
    orderid: str = Field(..., description="Order ID to modify")
    action: ActionType = Field(...)
    product: ProductType = Field(...)
    pricetype: PriceType = Field(...)
    price: float = Field(..., ge=0)
    quantity: int = Field(..., ge=1)
    disclosed_quantity: int = Field(..., ge=0)
    trigger_price: float = Field(..., ge=0)


class CancelOrderRequest(StrategyModel):
    """Request model for canceling an order"""
    orderid: str = Field(..., description="Order ID to cancel")


class ClosePositionRequest(StrategyModel):
    """Request model for closing all positions"""
    pass


class CancelAllOrderRequest(StrategyModel):
    """Request model for canceling all orders"""
    pass


# ============================================================
# Basket and Split Order Schemas
# ============================================================

class BasketOrderItem(BaseModel):
    """Single item in a basket order"""
    exchange: str = Field(...)
    symbol: str = Field(...)
    action: ActionType = Field(...)
    quantity: int = Field(..., ge=1)
    pricetype: PriceType = Field(default=PriceType.MARKET)
    product: ProductType = Field(default=ProductType.MIS)
    price: float = Field(default=0.0, ge=0)
    trigger_price: float = Field(default=0.0, ge=0)
    disclosed_quantity: int = Field(default=0, ge=0)


class BasketOrderRequest(StrategyModel):
    """Request model for basket orders"""
    orders: List[BasketOrderItem] = Field(..., min_length=1, description="List of orders")


class SplitOrderRequest(StrategyModel):
    """Request model for split orders"""
    exchange: str = Field(...)
    symbol: str = Field(...)
    action: ActionType = Field(...)
    quantity: int = Field(..., ge=1, description="Total quantity to split")
    splitsize: int = Field(..., ge=1, description="Size of each split")
    pricetype: PriceType = Field(default=PriceType.MARKET)
    product: ProductType = Field(default=ProductType.MIS)
    price: float = Field(default=0.0, ge=0)
    trigger_price: float = Field(default=0.0, ge=0)
    disclosed_quantity: int = Field(default=0, ge=0)


# ============================================================
# Options Order Schemas
# ============================================================

def validate_option_offset(offset: str) -> str:
    """Validate option offset: ATM, ITM1-ITM50, OTM1-OTM50"""
    offset_upper = offset.upper()
    if offset_upper == "ATM":
        return offset
    
    itm_pattern = re.compile(r"^ITM([1-9]|[1-4][0-9]|50)$")
    otm_pattern = re.compile(r"^OTM([1-9]|[1-4][0-9]|50)$")
    
    if not (itm_pattern.match(offset_upper) or otm_pattern.match(offset_upper)):
        raise ValueError("Offset must be ATM, ITM1-ITM50, or OTM1-OTM50")
    
    return offset


class OptionsOrderRequest(StrategyModel):
    """Request model for options orders"""
    underlying: str = Field(..., description="Underlying symbol (NIFTY, BANKNIFTY, etc.)")
    exchange: str = Field(..., description="Exchange")
    expiry_date: Optional[str] = Field(default=None, description="Expiry date in DDMMMYY format")
    strike_int: Optional[int] = Field(default=None, ge=1, description="Strike interval")
    offset: str = Field(..., description="ATM, ITM1-ITM50, OTM1-OTM50")
    option_type: OptionType = Field(..., description="CE or PE")
    action: ActionType = Field(...)
    quantity: int = Field(..., ge=1)
    splitsize: Optional[int] = Field(default=0, ge=0, description="Split size for large orders")
    pricetype: PriceType = Field(default=PriceType.MARKET)
    product: OptionsProductType = Field(default=OptionsProductType.MIS)
    price: float = Field(default=0.0, ge=0)
    trigger_price: float = Field(default=0.0, ge=0)
    disclosed_quantity: int = Field(default=0, ge=0)

    @field_validator('offset')
    @classmethod
    def validate_offset(cls, v):
        return validate_option_offset(v)


class OptionsMultiOrderLeg(BaseModel):
    """Single leg in options multi-order"""
    offset: str = Field(..., description="ATM, ITM1-ITM50, OTM1-OTM50")
    option_type: OptionType = Field(...)
    action: ActionType = Field(...)
    quantity: int = Field(..., ge=1)
    splitsize: Optional[int] = Field(default=0, ge=0)
    expiry_date: Optional[str] = Field(default=None, description="Per-leg expiry for calendar spreads")
    pricetype: PriceType = Field(default=PriceType.MARKET)
    product: OptionsProductType = Field(default=OptionsProductType.MIS)
    price: float = Field(default=0.0, ge=0)
    trigger_price: float = Field(default=0.0, ge=0)
    disclosed_quantity: int = Field(default=0, ge=0)

    @field_validator('offset')
    @classmethod
    def validate_offset(cls, v):
        return validate_option_offset(v)


class OptionsMultiOrderRequest(StrategyModel):
    """Request model for options multi-order with multiple legs"""
    underlying: str = Field(...)
    exchange: str = Field(...)
    expiry_date: Optional[str] = Field(default=None)
    strike_int: Optional[int] = Field(default=None, ge=1)
    legs: List[OptionsMultiOrderLeg] = Field(..., min_length=1, max_length=20)


class SyntheticFutureRequest(APIKeyModel):
    """Request model for synthetic future calculation"""
    underlying: str = Field(...)
    exchange: str = Field(...)
    expiry_date: str = Field(..., description="Expiry date in DDMMMYY format")


# ============================================================
# Account Schemas
# ============================================================

class FundsRequest(APIKeyModel):
    """Request model for funds query"""
    pass


class OrderbookRequest(APIKeyModel):
    """Request model for orderbook query"""
    pass


class TradebookRequest(APIKeyModel):
    """Request model for tradebook query"""
    pass


class PositionbookRequest(APIKeyModel):
    """Request model for positionbook query"""
    pass


class HoldingsRequest(APIKeyModel):
    """Request model for holdings query"""
    pass


class OrderStatusRequest(StrategyModel):
    """Request model for order status query"""
    orderid: str = Field(...)


class OpenPositionRequest(StrategyModel):
    """Request model for open position query"""
    symbol: str = Field(...)
    exchange: str = Field(...)
    product: ProductType = Field(...)


class AnalyzerRequest(APIKeyModel):
    """Request model for analyzer query"""
    pass


class AnalyzerToggleRequest(APIKeyModel):
    """Request model for analyzer toggle"""
    mode: bool = Field(..., description="Enable/disable analyzer mode")


class PingRequest(APIKeyModel):
    """Request model for ping"""
    pass


class ChartRequest(APIKeyModel):
    """Request model for chart preferences"""
    class Config:
        extra = "allow"  # Allow additional fields for chart preferences


class PnlSymbolsRequest(APIKeyModel):
    """Request model for PnL symbols"""
    pass


# ============================================================
# Market Data Schemas
# ============================================================

class QuotesRequest(APIKeyModel):
    """Request model for quotes"""
    symbol: str = Field(...)
    exchange: str = Field(...)


class SymbolExchangePair(BaseModel):
    """Symbol-exchange pair for multi-quotes"""
    symbol: str = Field(...)
    exchange: str = Field(...)


class MultiQuotesRequest(APIKeyModel):
    """Request model for multi-quotes"""
    symbols: List[SymbolExchangePair] = Field(..., min_length=1)


class HistoryRequest(APIKeyModel):
    """Request model for historical data"""
    symbol: str = Field(...)
    exchange: str = Field(...)
    interval: IntervalType = Field(...)
    start_date: date = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date (YYYY-MM-DD)")
    source: DataSource = Field(default=DataSource.api, description="Data source: api or db")


class DepthRequest(APIKeyModel):
    """Request model for market depth"""
    symbol: str = Field(...)
    exchange: str = Field(...)


class IntervalsRequest(APIKeyModel):
    """Request model for supported intervals"""
    pass


class SymbolRequest(APIKeyModel):
    """Request model for symbol info"""
    symbol: str = Field(...)
    exchange: str = Field(...)


def validate_date_or_timestamp(value: str) -> str:
    """Validate date (YYYY-MM-DD) or timestamp string"""
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    timestamp_pattern = re.compile(r"^\d{10,13}$")
    if not (date_pattern.match(value) or timestamp_pattern.match(value)):
        raise ValueError("Must be YYYY-MM-DD format or numeric timestamp")
    return value


class TickerRequest(APIKeyModel):
    """Request model for ticker data"""
    symbol: str = Field(..., description="Combined exchange:symbol format")
    interval: TickerIntervalType = Field(...)
    from_: str = Field(..., alias="from", description="Start date/timestamp")
    to: str = Field(..., description="End date/timestamp")
    adjusted: bool = Field(default=True, description="Adjust for splits")
    sort: SortDirection = Field(default=SortDirection.asc)

    @field_validator('from_', 'to')
    @classmethod
    def validate_date_timestamp(cls, v):
        return validate_date_or_timestamp(v)

    class Config:
        populate_by_name = True


class SearchRequest(APIKeyModel):
    """Request model for symbol search"""
    query: str = Field(..., description="Search query")
    exchange: Optional[str] = Field(default=None, description="Optional exchange filter")


class ExpiryRequest(APIKeyModel):
    """Request model for expiry dates"""
    symbol: str = Field(..., description="Underlying symbol")
    exchange: DerivativeExchange = Field(...)
    instrumenttype: InstrumentType = Field(...)


class InstrumentsRequest(APIKeyModel):
    """Request model for instruments list"""
    exchange: Optional[ExchangeType] = Field(default=None)
    format: OutputFormat = Field(default=OutputFormat.json)


# ============================================================
# Options Data Schemas
# ============================================================

class OptionSymbolRequest(APIKeyModel):
    """Request model for option symbol lookup"""
    strategy: Optional[str] = Field(default=None, description="Deprecated: Strategy name")
    underlying: str = Field(..., description="Underlying symbol")
    exchange: str = Field(...)
    expiry_date: Optional[str] = Field(default=None, description="Expiry in DDMMMYY format")
    strike_int: Optional[int] = Field(default=None, ge=1)
    offset: str = Field(..., description="ATM, ITM1-ITM50, OTM1-OTM50")
    option_type: OptionType = Field(...)

    @field_validator('offset')
    @classmethod
    def validate_offset(cls, v):
        return validate_option_offset(v)


class OptionGreeksRequest(APIKeyModel):
    """Request model for option greeks"""
    symbol: str = Field(..., description="Option symbol")
    exchange: DerivativeExchange = Field(...)
    interest_rate: Optional[float] = Field(default=None, ge=0, le=100)
    forward_price: Optional[float] = Field(default=None, ge=0)
    underlying_symbol: Optional[str] = Field(default=None)
    underlying_exchange: Optional[str] = Field(default=None)
    expiry_time: Optional[str] = Field(default=None, description="HH:MM format")


class OptionSymbolForGreeks(BaseModel):
    """Single option symbol for batch greeks"""
    symbol: str = Field(...)
    exchange: DerivativeExchange = Field(...)
    underlying_symbol: Optional[str] = Field(default=None)
    underlying_exchange: Optional[str] = Field(default=None)


class MultiOptionGreeksRequest(APIKeyModel):
    """Request model for batch option greeks"""
    symbols: List[OptionSymbolForGreeks] = Field(..., min_length=1, max_length=50)
    interest_rate: Optional[float] = Field(default=None, ge=0, le=100)
    expiry_time: Optional[str] = Field(default=None)


class OptionChainRequest(APIKeyModel):
    """Request model for option chain"""
    underlying: str = Field(...)
    exchange: str = Field(...)
    expiry_date: str = Field(..., description="Expiry in DDMMMYY format")
    strike_count: Optional[int] = Field(default=None, ge=1, le=100)


# ============================================================
# Margin Schemas
# ============================================================

class MarginPosition(BaseModel):
    """Single position for margin calculation"""
    symbol: str = Field(..., min_length=1, max_length=50)
    exchange: Literal["NSE", "BSE", "NFO", "BFO", "CDS", "MCX"] = Field(...)
    action: ActionType = Field(...)
    quantity: str = Field(..., description="Quantity as string")
    product: ProductType = Field(...)
    pricetype: PriceType = Field(...)
    price: str = Field(default="0")
    trigger_price: str = Field(default="0")


class MarginCalculatorRequest(APIKeyModel):
    """Request model for margin calculator"""
    positions: List[MarginPosition] = Field(..., min_length=1, max_length=50)


# ============================================================
# Market Calendar Schemas
# ============================================================

class MarketHolidaysRequest(APIKeyModel):
    """Request model for market holidays"""
    year: Optional[int] = Field(default=None, ge=2020, le=2050)


class MarketTimingsRequest(APIKeyModel):
    """Request model for market timings"""
    date: str = Field(..., description="Date in YYYY-MM-DD format")


# ============================================================
# Response Models
# ============================================================

class BaseResponse(BaseModel):
    """Base response model"""
    status: str = Field(..., description="success or error")


class SuccessResponse(BaseResponse):
    """Success response model"""
    status: Literal["success"] = "success"
    data: Optional[Any] = None


class ErrorResponse(BaseResponse):
    """Error response model"""
    status: Literal["error"] = "error"
    message: str = Field(..., description="Error message")


class OrderResponse(BaseResponse):
    """Response model for order operations"""
    orderid: Optional[str] = None
    message: Optional[str] = None


class FundsResponse(BaseResponse):
    """Response model for funds query"""
    data: Optional[Dict[str, Any]] = None


class QuotesResponse(BaseResponse):
    """Response model for quotes"""
    data: Optional[Dict[str, Any]] = None


class HistoryResponse(BaseResponse):
    """Response model for historical data"""
    data: Optional[List[Dict[str, Any]]] = None


class PositionsResponse(BaseResponse):
    """Response model for positions"""
    data: Optional[List[Dict[str, Any]]] = None


class OrderbookResponse(BaseResponse):
    """Response model for orderbook"""
    data: Optional[List[Dict[str, Any]]] = None


class HoldingsResponse(BaseResponse):
    """Response model for holdings"""
    data: Optional[List[Dict[str, Any]]] = None


class OptionChainResponse(BaseResponse):
    """Response model for option chain"""
    data: Optional[Dict[str, Any]] = None


class OptionGreeksResponse(BaseResponse):
    """Response model for option greeks"""
    data: Optional[Dict[str, Any]] = None


class InstrumentsResponse(BaseResponse):
    """Response model for instruments"""
    data: Optional[List[Dict[str, Any]]] = None


class PingResponse(BaseResponse):
    """Response model for ping"""
    message: str = "pong"
