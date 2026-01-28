# routers/orders.py
"""
FastAPI Orders Router for RealAlgo
Handles order-related routes: orderbook, tradebook, positions, holdings,
CSV exports, close/cancel/modify orders, and action center.
Requirements: 4.1, 4.2, 4.3, 4.4
"""

import csv
import io
from importlib import import_module
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from database.auth_db import get_api_key_for_tradingview, get_auth_token
from database.settings_db import get_analyze_mode
from dependencies_fastapi import check_session_validity, get_session
from limiter_fastapi import limiter, API_RATE_LIMIT
from services.close_position_service import close_position as close_position_service
from services.holdings_service import get_holdings
from services.orderbook_service import get_orderbook
from services.positionbook_service import get_positionbook
from services.tradebook_service import get_tradebook
from utils.logging import get_logger

logger = get_logger(__name__)
orders_router = APIRouter(prefix="", tags=["orders"])
templates = Jinja2Templates(directory="templates")


def dynamic_import(broker: str, module_name: str, function_names: list) -> Optional[Dict]:
    """Dynamically import broker-specific functions."""
    module_functions = {}
    try:
        module = import_module(f"broker.{broker}.{module_name}")
        for name in function_names:
            module_functions[name] = getattr(module, name)
        return module_functions
    except (ImportError, AttributeError) as e:
        logger.error(f"Error importing {function_names} from {module_name} for {broker}: {e}")
        return None


def generate_orderbook_csv(order_data: list) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ["Trading Symbol", "Exchange", "Transaction Type", "Quantity", "Price",
               "Trigger Price", "Order Type", "Product Type", "Order ID", "Status", "Time"]
    writer.writerow(headers)
    for order in order_data:
        writer.writerow([order.get("symbol", ""), order.get("exchange", ""), order.get("action", ""),
                        order.get("quantity", ""), order.get("price", ""), order.get("trigger_price", ""),
                        order.get("pricetype", ""), order.get("product", ""), order.get("orderid", ""),
                        order.get("order_status", ""), order.get("timestamp", "")])
    return output.getvalue()


def generate_tradebook_csv(trade_data: list) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ["Trading Symbol", "Exchange", "Product Type", "Transaction Type",
               "Fill Size", "Fill Price", "Trade Value", "Order ID", "Fill Time"]
    writer.writerow(headers)
    for trade in trade_data:
        writer.writerow([trade.get("symbol", ""), trade.get("exchange", ""), trade.get("product", ""),
                        trade.get("action", ""), trade.get("quantity", ""), trade.get("average_price", ""),
                        trade.get("trade_value", ""), trade.get("orderid", ""), trade.get("timestamp", "")])
    return output.getvalue()


def generate_positions_csv(positions_data: list) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ["Symbol", "Exchange", "Product Type", "Net Qty", "Avg Price", "LTP", "P&L"]
    writer.writerow(headers)
    for position in positions_data:
        writer.writerow([position.get("symbol", ""), position.get("exchange", ""),
                        position.get("product", ""), position.get("quantity", ""),
                        position.get("average_price", ""), position.get("ltp", ""),
                        position.get("pnl", "")])
    return output.getvalue()



@orders_router.get("/orderbook")
@limiter.limit(API_RATE_LIMIT)
async def orderbook(request: Request, session: dict = Depends(check_session_validity)):
    """Display orderbook page."""
    login_username = session["user"]
    auth_token = get_auth_token(login_username)

    if auth_token is None:
        logger.warning(f"No auth token found for user {login_username}")
        return RedirectResponse(url="/auth/logout", status_code=302)

    broker = session.get("broker")
    if not broker:
        logger.error("Broker not set in session")
        return Response(content="Broker not set in session", status_code=400)

    if get_analyze_mode():
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_orderbook(api_key=api_key)
        else:
            logger.error("No API key found for analyze mode")
            return Response(content="API key required for analyze mode", status_code=400)
    else:
        success, response, status_code = get_orderbook(auth_token=auth_token, broker=broker)

    if not success:
        logger.error(f"Failed to get orderbook data: {response.get('message', 'Unknown error')}")
        if status_code == 404:
            return Response(content="Failed to import broker module", status_code=500)
        return RedirectResponse(url="/auth/logout", status_code=302)

    data = response.get("data", {})
    order_data = data.get("orders", [])
    order_stats = data.get("statistics", {})

    return templates.TemplateResponse("orderbook.html", {
        "request": request, "order_data": order_data, "order_stats": order_stats
    })


@orders_router.get("/tradebook")
@limiter.limit(API_RATE_LIMIT)
async def tradebook(request: Request, session: dict = Depends(check_session_validity)):
    """Display tradebook page."""
    login_username = session["user"]
    auth_token = get_auth_token(login_username)

    if auth_token is None:
        logger.warning(f"No auth token found for user {login_username}")
        return RedirectResponse(url="/auth/logout", status_code=302)

    broker = session.get("broker")
    if not broker:
        logger.error("Broker not set in session")
        return Response(content="Broker not set in session", status_code=400)

    if get_analyze_mode():
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_tradebook(api_key=api_key)
        else:
            logger.error("No API key found for analyze mode")
            return Response(content="API key required for analyze mode", status_code=400)
    else:
        success, response, status_code = get_tradebook(auth_token=auth_token, broker=broker)

    if not success:
        logger.error(f"Failed to get tradebook data: {response.get('message', 'Unknown error')}")
        if status_code == 404:
            return Response(content="Failed to import broker module", status_code=500)
        return RedirectResponse(url="/auth/logout", status_code=302)

    tradebook_data = response.get("data", [])
    return templates.TemplateResponse("tradebook.html", {
        "request": request, "tradebook_data": tradebook_data
    })


@orders_router.get("/positions")
@limiter.limit(API_RATE_LIMIT)
async def positions(request: Request, session: dict = Depends(check_session_validity)):
    """Display positions page."""
    login_username = session["user"]
    auth_token = get_auth_token(login_username)

    if auth_token is None:
        logger.warning(f"No auth token found for user {login_username}")
        return RedirectResponse(url="/auth/logout", status_code=302)

    broker = session.get("broker")
    if not broker:
        logger.error("Broker not set in session")
        return Response(content="Broker not set in session", status_code=400)

    if get_analyze_mode():
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_positionbook(api_key=api_key)
        else:
            logger.error("No API key found for analyze mode")
            return Response(content="API key required for analyze mode", status_code=400)
    else:
        success, response, status_code = get_positionbook(auth_token=auth_token, broker=broker)

    if not success:
        logger.error(f"Failed to get positions data: {response.get('message', 'Unknown error')}")
        if status_code == 404:
            return Response(content="Failed to import broker module", status_code=500)
        return RedirectResponse(url="/auth/logout", status_code=302)

    positions_data = response.get("data", [])
    return templates.TemplateResponse("positions.html", {
        "request": request, "positions_data": positions_data
    })


@orders_router.get("/holdings")
@limiter.limit(API_RATE_LIMIT)
async def holdings(request: Request, session: dict = Depends(check_session_validity)):
    """Display holdings page."""
    login_username = session["user"]
    auth_token = get_auth_token(login_username)

    if auth_token is None:
        logger.warning(f"No auth token found for user {login_username}")
        return RedirectResponse(url="/auth/logout", status_code=302)

    broker = session.get("broker")
    if not broker:
        logger.error("Broker not set in session")
        return Response(content="Broker not set in session", status_code=400)

    if get_analyze_mode():
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_holdings(api_key=api_key)
        else:
            logger.error("No API key found for analyze mode")
            return Response(content="API key required for analyze mode", status_code=400)
    else:
        success, response, status_code = get_holdings(auth_token=auth_token, broker=broker)

    if not success:
        logger.error(f"Failed to get holdings data: {response.get('message', 'Unknown error')}")
        if status_code == 404:
            return Response(content="Failed to import broker module", status_code=500)
        return RedirectResponse(url="/auth/logout", status_code=302)

    data = response.get("data", {})
    holdings_data = data.get("holdings", [])
    portfolio_stats = data.get("statistics", {})

    return templates.TemplateResponse("holdings.html", {
        "request": request, "holdings_data": holdings_data, "portfolio_stats": portfolio_stats
    })


@orders_router.get("/orderbook/export")
@limiter.limit(API_RATE_LIMIT)
async def export_orderbook(request: Request, session: dict = Depends(check_session_validity)):
    """Export orderbook as CSV."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")

        if auth_token is None:
            logger.warning(f"No auth token found for user {login_username}")
            return RedirectResponse(url="/auth/logout", status_code=302)

        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if api_key:
                success, response, status_code = get_orderbook(api_key=api_key)
                if not success:
                    logger.error("Failed to get orderbook data in analyze mode")
                    return Response(content="Error getting orderbook data", status_code=500)
                data = response.get("data", {})
                order_data = data.get("orders", [])
            else:
                logger.error("No API key found for analyze mode")
                return Response(content="API key required for analyze mode", status_code=400)
        else:
            if not broker:
                logger.error("Broker not set in session")
                return Response(content="Broker not set in session", status_code=400)

            api_funcs = dynamic_import(broker, "api.order_api", ["get_order_book"])
            mapping_funcs = dynamic_import(broker, "mapping.order_data", ["map_order_data", "transform_order_data"])

            if not api_funcs or not mapping_funcs:
                logger.error(f"Error loading broker-specific modules for {broker}")
                return Response(content="Error loading broker-specific modules", status_code=500)

            order_data = api_funcs["get_order_book"](auth_token)
            if "status" in order_data and order_data["status"] == "error":
                logger.error("Error in order data response")
                return RedirectResponse(url="/auth/logout", status_code=302)

            order_data = mapping_funcs["map_order_data"](order_data=order_data)
            order_data = mapping_funcs["transform_order_data"](order_data)

        csv_data = generate_orderbook_csv(order_data)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=orderbook.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting orderbook: {str(e)}")
        return Response(content="Error exporting orderbook", status_code=500)


@orders_router.get("/tradebook/export")
@limiter.limit(API_RATE_LIMIT)
async def export_tradebook(request: Request, session: dict = Depends(check_session_validity)):
    """Export tradebook as CSV."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")

        if auth_token is None:
            logger.warning(f"No auth token found for user {login_username}")
            return RedirectResponse(url="/auth/logout", status_code=302)

        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if api_key:
                success, response, status_code = get_tradebook(api_key=api_key)
                if not success:
                    logger.error("Failed to get tradebook data in analyze mode")
                    return Response(content="Error getting tradebook data", status_code=500)
                tradebook_data = response.get("data", [])
            else:
                logger.error("No API key found for analyze mode")
                return Response(content="API key required for analyze mode", status_code=400)
        else:
            if not broker:
                logger.error("Broker not set in session")
                return Response(content="Broker not set in session", status_code=400)

            api_funcs = dynamic_import(broker, "api.order_api", ["get_trade_book"])
            mapping_funcs = dynamic_import(broker, "mapping.order_data", ["map_trade_data", "transform_tradebook_data"])

            if not api_funcs or not mapping_funcs:
                logger.error(f"Error loading broker-specific modules for {broker}")
                return Response(content="Error loading broker-specific modules", status_code=500)

            tradebook_data = api_funcs["get_trade_book"](auth_token)
            if "status" in tradebook_data and tradebook_data["status"] == "error":
                logger.error("Error in tradebook data response")
                return RedirectResponse(url="/auth/logout", status_code=302)

            tradebook_data = mapping_funcs["map_trade_data"](tradebook_data)
            tradebook_data = mapping_funcs["transform_tradebook_data"](tradebook_data)

        csv_data = generate_tradebook_csv(tradebook_data)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=tradebook.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting tradebook: {str(e)}")
        return Response(content="Error exporting tradebook", status_code=500)


@orders_router.get("/positions/export")
@limiter.limit(API_RATE_LIMIT)
async def export_positions(request: Request, session: dict = Depends(check_session_validity)):
    """Export positions as CSV."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")

        if auth_token is None:
            logger.warning(f"No auth token found for user {login_username}")
            return RedirectResponse(url="/auth/logout", status_code=302)

        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if api_key:
                success, response, status_code = get_positionbook(api_key=api_key)
                if not success:
                    logger.error("Failed to get positions data in analyze mode")
                    return Response(content="Error getting positions data", status_code=500)
                positions_data = response.get("data", [])
            else:
                logger.error("No API key found for analyze mode")
                return Response(content="API key required for analyze mode", status_code=400)
        else:
            if not broker:
                logger.error("Broker not set in session")
                return Response(content="Broker not set in session", status_code=400)

            api_funcs = dynamic_import(broker, "api.order_api", ["get_positions"])
            mapping_funcs = dynamic_import(broker, "mapping.order_data", ["map_position_data", "transform_positions_data"])

            if not api_funcs or not mapping_funcs:
                logger.error(f"Error loading broker-specific modules for {broker}")
                return Response(content="Error loading broker-specific modules", status_code=500)

            positions_data = api_funcs["get_positions"](auth_token)
            if "status" in positions_data and positions_data["status"] == "error":
                logger.error("Error in positions data response")
                return RedirectResponse(url="/auth/logout", status_code=302)

            positions_data = mapping_funcs["map_position_data"](positions_data)
            positions_data = mapping_funcs["transform_positions_data"](positions_data)

        csv_data = generate_positions_csv(positions_data)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=positions.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting positions: {str(e)}")
        return Response(content="Error exporting positions", status_code=500)


@orders_router.post("/close_position")
@limiter.limit(API_RATE_LIMIT)
async def close_position_route(request: Request, session: dict = Depends(check_session_validity)):
    """Close a specific position."""
    try:
        data = await request.json()
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        product = data.get("product")

        if not all([symbol, exchange, product]):
            return JSONResponse(
                {"status": "error", "message": "Missing required parameters (symbol, exchange, product)"},
                status_code=400
            )

        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")

        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if not api_key:
                return JSONResponse({"status": "error", "message": "API key not found for analyze mode"}, status_code=401)

            order_data = {
                "strategy": "UI Exit Position",
                "exchange": exchange,
                "symbol": symbol,
                "action": "BUY",
                "product_type": product,
                "pricetype": "MARKET",
                "quantity": "0",
                "price": "0",
                "trigger_price": "0",
                "disclosed_quantity": "0",
                "position_size": "0",
            }

            from services.place_smart_order_service import place_smart_order
            success, response_data, status_code = place_smart_order(order_data=order_data, api_key=api_key)
            return JSONResponse(response_data, status_code=status_code)

        if not auth_token or not broker_name:
            return JSONResponse({"status": "error", "message": "Authentication error"}, status_code=401)

        api_funcs = dynamic_import(broker_name, "api.order_api", ["place_smartorder_api", "get_open_position"])
        if not api_funcs:
            logger.error(f"Error loading broker-specific modules for {broker_name}")
            return JSONResponse({"status": "error", "message": "Error loading broker modules"}, status_code=500)

        place_smartorder_api = api_funcs["place_smartorder_api"]
        order_data = {
            "strategy": "UI Exit Position",
            "exchange": exchange,
            "symbol": symbol,
            "action": "BUY",
            "product": product,
            "pricetype": "MARKET",
            "quantity": "0",
            "price": "0",
            "trigger_price": "0",
            "disclosed_quantity": "0",
            "position_size": "0",
        }

        res, response, orderid = place_smartorder_api(order_data, auth_token)

        if orderid:
            response_data = {
                "status": "success",
                "message": response.get("message") if response and "message" in response else "Position close order placed successfully.",
                "orderid": orderid,
            }
            return JSONResponse(response_data, status_code=200)
        else:
            response_data = {
                "status": "error",
                "message": response.get("message") if response and "message" in response else "Failed to close position.",
            }
            status_code = res.status if res and hasattr(res, "status") and isinstance(res.status, int) and res.status >= 400 else 400
            return JSONResponse(response_data, status_code=status_code)

    except Exception as e:
        logger.error(f"Error in close_position endpoint: {str(e)}")
        return JSONResponse({"status": "error", "message": f"An error occurred: {str(e)}"}, status_code=500)


@orders_router.post("/close_all_positions")
@limiter.limit(API_RATE_LIMIT)
async def close_all_positions(request: Request, session: dict = Depends(check_session_validity)):
    """Close all open positions."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")

        if not auth_token or not broker_name:
            return JSONResponse({"status": "error", "message": "Authentication error"}, status_code=401)

        api_key = None
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)

        success, response_data, status_code = close_position_service(
            position_data={}, api_key=api_key, auth_token=auth_token, broker=broker_name
        )

        if success and status_code == 200:
            return JSONResponse({
                "status": "success",
                "message": response_data.get("message", "All Open Positions Squared Off"),
            }, status_code=200)
        else:
            return JSONResponse(response_data, status_code=status_code)

    except Exception as e:
        logger.error(f"Error in close_all_positions endpoint: {str(e)}")
        return JSONResponse({"status": "error", "message": f"An error occurred: {str(e)}"}, status_code=500)


@orders_router.post("/cancel_all_orders")
@limiter.limit(API_RATE_LIMIT)
async def cancel_all_orders_ui(request: Request, session: dict = Depends(check_session_validity)):
    """Cancel all open orders from UI."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")

        if not auth_token or not broker_name:
            return JSONResponse({"status": "error", "message": "Authentication error"}, status_code=401)

        from services.cancel_all_order_service import cancel_all_orders

        api_key = None
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)

        success, response_data, status_code = cancel_all_orders(
            order_data={}, api_key=api_key, auth_token=auth_token, broker=broker_name
        )

        if success and status_code == 200:
            canceled_count = len(response_data.get("canceled_orders", []))
            failed_count = len(response_data.get("failed_cancellations", []))

            if canceled_count > 0 or failed_count == 0:
                message = f"Successfully canceled {canceled_count} orders"
                if failed_count > 0:
                    message += f" (Failed to cancel {failed_count} orders)"
                return JSONResponse({
                    "status": "success",
                    "message": message,
                    "canceled_orders": response_data.get("canceled_orders", []),
                    "failed_cancellations": response_data.get("failed_cancellations", []),
                }, status_code=200)
            else:
                return JSONResponse({"status": "info", "message": "No open orders to cancel"}, status_code=200)
        else:
            return JSONResponse(response_data, status_code=status_code)

    except Exception as e:
        logger.error(f"Error in cancel_all_orders_ui endpoint: {str(e)}")
        return JSONResponse({"status": "error", "message": f"An error occurred: {str(e)}"}, status_code=500)


@orders_router.post("/cancel_order")
@limiter.limit(API_RATE_LIMIT)
async def cancel_order_ui(request: Request, session: dict = Depends(check_session_validity)):
    """Cancel a single order from UI."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")

        if not auth_token or not broker_name:
            return JSONResponse({"status": "error", "message": "Authentication error"}, status_code=401)

        data = await request.json()
        orderid = data.get("orderid")

        if not orderid:
            return JSONResponse({"status": "error", "message": "Order ID is required"}, status_code=400)

        from services.cancel_order_service import cancel_order

        api_key = None
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)

        success, response_data, status_code = cancel_order(
            orderid=orderid, api_key=api_key, auth_token=auth_token, broker=broker_name
        )

        return JSONResponse(response_data, status_code=status_code)

    except Exception as e:
        logger.error(f"Error in cancel_order_ui endpoint: {str(e)}")
        return JSONResponse({"status": "error", "message": f"An error occurred: {str(e)}"}, status_code=500)


@orders_router.post("/modify_order")
@limiter.limit(API_RATE_LIMIT)
async def modify_order_ui(request: Request, session: dict = Depends(check_session_validity)):
    """Modify an order from UI."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")

        if not auth_token or not broker_name:
            return JSONResponse({"status": "error", "message": "Authentication error"}, status_code=401)

        data = await request.json()
        orderid = data.get("orderid")

        if not orderid:
            return JSONResponse({"status": "error", "message": "Order ID is required"}, status_code=400)

        from services.modify_order_service import modify_order

        api_key = None
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)

        order_data = {
            "orderid": orderid,
            "symbol": data.get("symbol"),
            "exchange": data.get("exchange"),
            "action": data.get("action"),
            "product": data.get("product"),
            "pricetype": data.get("pricetype"),
            "price": data.get("price"),
            "quantity": data.get("quantity"),
            "disclosed_quantity": data.get("disclosed_quantity", 0),
            "trigger_price": data.get("trigger_price", 0),
        }

        success, response_data, status_code = modify_order(
            order_data=order_data, api_key=api_key, auth_token=auth_token, broker=broker_name
        )

        return JSONResponse(response_data, status_code=status_code)

    except Exception as e:
        logger.error(f"Error in modify_order_ui endpoint: {str(e)}")
        return JSONResponse({"status": "error", "message": f"An error occurred: {str(e)}"}, status_code=500)


# Action Center Routes

@orders_router.get("/action-center")
@limiter.limit(API_RATE_LIMIT)
async def action_center(request: Request, status: str = Query("pending"), session: dict = Depends(check_session_validity)):
    """Action Center - Manage pending semi-automated orders."""
    login_username = session["user"]
    status_filter = status

    from services.action_center_service import get_action_center_data

    if status_filter == "all":
        success, response, status_code = get_action_center_data(login_username, status_filter=None)
    else:
        success, response, status_code = get_action_center_data(login_username, status_filter=status_filter)

    if not success:
        logger.error(f"Failed to get action center data: {response.get('message', 'Unknown error')}")
        return templates.TemplateResponse("action_center.html", {
            "request": request,
            "order_data": [],
            "order_stats": {},
            "current_filter": status_filter,
            "login_username": login_username,
        })

    data = response.get("data", {})
    order_data = data.get("orders", [])
    order_stats = data.get("statistics", {})

    return templates.TemplateResponse("action_center.html", {
        "request": request,
        "order_data": order_data,
        "order_stats": order_stats,
        "current_filter": status_filter,
        "login_username": login_username,
    })


@orders_router.post("/action-center/approve/{order_id}")
@limiter.limit(API_RATE_LIMIT)
async def approve_pending_order_route(order_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Approve a pending order and execute it."""
    login_username = session["user"]

    from database.action_center_db import approve_pending_order
    from extensions import socketio
    from services.pending_order_execution_service import execute_approved_order

    success = approve_pending_order(order_id, login_username, login_username)

    if success:
        exec_success, response_data, status_code = execute_approved_order(order_id)

        socketio.emit("pending_order_updated", {
            "action": "approved", "order_id": order_id, "user_id": login_username
        })

        if exec_success:
            return JSONResponse({
                "status": "success",
                "message": "Order approved and executed successfully",
                "broker_order_id": response_data.get("orderid"),
            })
        else:
            return JSONResponse({
                "status": "warning",
                "message": "Order approved but execution failed",
                "error": response_data.get("message"),
            }, status_code=status_code)
    else:
        return JSONResponse({"status": "error", "message": "Failed to approve order"}, status_code=400)


@orders_router.post("/action-center/reject/{order_id}")
@limiter.limit(API_RATE_LIMIT)
async def reject_pending_order_route(order_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Reject a pending order."""
    login_username = session["user"]
    data = await request.json()
    reason = data.get("reason", "No reason provided")

    from database.action_center_db import reject_pending_order
    from extensions import socketio

    success = reject_pending_order(order_id, reason, login_username, login_username)

    if success:
        socketio.emit("pending_order_updated", {
            "action": "rejected", "order_id": order_id, "user_id": login_username
        })
        return JSONResponse({"status": "success", "message": "Order rejected successfully"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to reject order"}, status_code=400)


@orders_router.delete("/action-center/delete/{order_id}")
@limiter.limit(API_RATE_LIMIT)
async def delete_pending_order_route(order_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Delete a pending order (only if not pending)."""
    login_username = session["user"]

    from database.action_center_db import delete_pending_order
    from extensions import socketio

    success = delete_pending_order(order_id, login_username)

    if success:
        socketio.emit("pending_order_updated", {
            "action": "deleted", "order_id": order_id, "user_id": login_username
        })
        return JSONResponse({"status": "success", "message": "Order deleted successfully"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to delete order"}, status_code=400)


@orders_router.get("/action-center/count")
async def action_center_count(request: Request, session: dict = Depends(check_session_validity)):
    """Get count of pending orders for badge."""
    login_username = session["user"]

    from database.action_center_db import get_pending_count

    count = get_pending_count(login_username)
    return JSONResponse({"count": count})


@orders_router.post("/action-center/approve-all")
@limiter.limit(API_RATE_LIMIT)
async def approve_all_pending_orders(request: Request, session: dict = Depends(check_session_validity)):
    """Approve and execute all pending orders."""
    login_username = session["user"]

    from database.action_center_db import approve_pending_order, get_pending_orders
    from extensions import socketio
    from services.pending_order_execution_service import execute_approved_order

    pending_orders = get_pending_orders(login_username, status="pending")

    if not pending_orders:
        return JSONResponse({"status": "info", "message": "No pending orders to approve"}, status_code=200)

    approved_count = 0
    executed_count = 0
    failed_executions = []

    for order in pending_orders:
        success = approve_pending_order(order.id, login_username, login_username)

        if success:
            approved_count += 1
            exec_success, response_data, status_code = execute_approved_order(order.id)

            if exec_success:
                executed_count += 1
            else:
                failed_executions.append({
                    "order_id": order.id, "error": response_data.get("message", "Unknown error")
                })

    socketio.emit("pending_order_updated", {
        "action": "batch_approved", "user_id": login_username, "count": approved_count
    })

    if approved_count == executed_count:
        message = f"Successfully approved and executed all {approved_count} orders"
        status = "success"
    elif executed_count > 0:
        message = f"Approved {approved_count} orders. {executed_count} executed successfully, {len(failed_executions)} failed"
        status = "warning"
    else:
        message = f"Approved {approved_count} orders but all executions failed"
        status = "error"

    return JSONResponse({
        "status": status,
        "message": message,
        "approved_count": approved_count,
        "executed_count": executed_count,
        "failed_executions": failed_executions,
    }, status_code=200)


@orders_router.get("/action-center/api/data")
@limiter.limit(API_RATE_LIMIT)
async def action_center_api_data(request: Request, status: str = Query("pending"), session: dict = Depends(check_session_validity)):
    """Action Center JSON API - Get pending/approved/rejected orders data for React SPA."""
    login_username = session["user"]
    status_filter = status

    from services.action_center_service import get_action_center_data

    if status_filter == "all" or not status_filter:
        success, response, status_code = get_action_center_data(login_username, status_filter=None)
    else:
        success, response, status_code = get_action_center_data(login_username, status_filter=status_filter)

    if not success:
        logger.error(f"Failed to get action center data: {response.get('message', 'Unknown error')}")
        return JSONResponse({
            "status": "error",
            "message": response.get("message", "Failed to get action center data"),
            "data": {
                "orders": [],
                "statistics": {
                    "total_pending": 0,
                    "total_approved": 0,
                    "total_rejected": 0,
                    "total_buy_orders": 0,
                    "total_sell_orders": 0,
                },
            },
        }, status_code=status_code)

    return JSONResponse({"status": "success", "data": response.get("data", {})})
