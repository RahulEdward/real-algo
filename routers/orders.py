# routers/orders.py
"""
FastAPI Orders Router for RealAlgo
"""

import csv
import io
from importlib import import_module
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from database.auth_db import get_api_key_for_tradingview, get_auth_token
from database.settings_db import get_analyze_mode
from dependencies_fastapi import check_session_validity
from limiter_fastapi import limiter, API_RATE_LIMIT
from services.close_position_service import close_position as close_position_service
from services.holdings_service import get_holdings
from services.orderbook_service import get_orderbook
from services.positionbook_service import get_positionbook
from services.tradebook_service import get_tradebook
from utils.logging import get_logger

logger = get_logger(__name__)
orders_router = APIRouter(prefix="", tags=["orders"])


def dynamic_import(broker: str, module_name: str, function_names: list) -> Optional[Dict]:
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
        writer.writerow([position.get("symbol", ""), position.get("exchange", ""), position.get("product", ""),
                        position.get("quantity", ""), position.get("average_price", ""),
                        position.get("ltp", ""), position.get("pnl", "")])
    return output.getvalue()


@orders_router.get("/orderbook")
@limiter.limit(API_RATE_LIMIT)
async def orderbook(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    auth_token = get_auth_token(login_username)
    if auth_token is None:
        return RedirectResponse(url="/auth/logout", status_code=302)
    broker = session.get("broker")
    if not broker:
        return Response(content="Broker not set in session", status_code=400)
    if get_analyze_mode():
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_orderbook(api_key=api_key)
        else:
            return Response(content="API key required for analyze mode", status_code=400)
    else:
        success, response, status_code = get_orderbook(auth_token=auth_token, broker=broker)
    if not success:
        if status_code == 404:
            return Response(content="Failed to import broker module", status_code=500)
        return RedirectResponse(url="/auth/logout", status_code=302)
    return JSONResponse(content={"status": "success", "data": response.get("data", {})})


@orders_router.get("/tradebook")
@limiter.limit(API_RATE_LIMIT)
async def tradebook(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    auth_token = get_auth_token(login_username)
    if auth_token is None:
        return RedirectResponse(url="/auth/logout", status_code=302)
    broker = session.get("broker")
    if not broker:
        return Response(content="Broker not set in session", status_code=400)
    if get_analyze_mode():
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_tradebook(api_key=api_key)
        else:
            return Response(content="API key required for analyze mode", status_code=400)
    else:
        success, response, status_code = get_tradebook(auth_token=auth_token, broker=broker)
    if not success:
        if status_code == 404:
            return Response(content="Failed to import broker module", status_code=500)
        return RedirectResponse(url="/auth/logout", status_code=302)
    return JSONResponse(content={"status": "success", "data": response.get("data", [])})


@orders_router.get("/positions")
@limiter.limit(API_RATE_LIMIT)
async def positions(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    auth_token = get_auth_token(login_username)
    if auth_token is None:
        return RedirectResponse(url="/auth/logout", status_code=302)
    broker = session.get("broker")
    if not broker:
        return Response(content="Broker not set in session", status_code=400)
    if get_analyze_mode():
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_positionbook(api_key=api_key)
        else:
            return Response(content="API key required for analyze mode", status_code=400)
    else:
        success, response, status_code = get_positionbook(auth_token=auth_token, broker=broker)
    if not success:
        if status_code == 404:
            return Response(content="Failed to import broker module", status_code=500)
        return RedirectResponse(url="/auth/logout", status_code=302)
    return JSONResponse(content={"status": "success", "data": response.get("data", [])})


@orders_router.get("/holdings")
@limiter.limit(API_RATE_LIMIT)
async def holdings(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    auth_token = get_auth_token(login_username)
    if auth_token is None:
        return RedirectResponse(url="/auth/logout", status_code=302)
    broker = session.get("broker")
    if not broker:
        return Response(content="Broker not set in session", status_code=400)
    if get_analyze_mode():
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_holdings(api_key=api_key)
        else:
            return Response(content="API key required for analyze mode", status_code=400)
    else:
        success, response, status_code = get_holdings(auth_token=auth_token, broker=broker)
    if not success:
        if status_code == 404:
            return Response(content="Failed to import broker module", status_code=500)
        return RedirectResponse(url="/auth/logout", status_code=302)
    return JSONResponse(content={"status": "success", "data": response.get("data", {})})


@orders_router.get("/orderbook/export")
@limiter.limit(API_RATE_LIMIT)
async def export_orderbook(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")
        if auth_token is None:
            return RedirectResponse(url="/auth/logout", status_code=302)
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if api_key:
                success, response, status_code = get_orderbook(api_key=api_key)
                if not success:
                    return Response(content="Error getting orderbook data", status_code=500)
                order_data = response.get("data", {}).get("orders", [])
            else:
                return Response(content="API key required for analyze mode", status_code=400)
        else:
            if not broker:
                return Response(content="Broker not set in session", status_code=400)
            api_funcs = dynamic_import(broker, "api.order_api", ["get_order_book"])
            mapping_funcs = dynamic_import(broker, "mapping.order_data", ["map_order_data", "transform_order_data"])
            if not api_funcs or not mapping_funcs:
                return Response(content="Error loading broker-specific modules", status_code=500)
            order_data = api_funcs["get_order_book"](auth_token)
            if "status" in order_data and order_data["status"] == "error":
                return RedirectResponse(url="/auth/logout", status_code=302)
            order_data = mapping_funcs["map_order_data"](order_data=order_data)
            order_data = mapping_funcs["transform_order_data"](order_data)
        csv_data = generate_orderbook_csv(order_data)
        return Response(content=csv_data, media_type="text/csv",
                       headers={"Content-Disposition": "attachment; filename=orderbook.csv"})
    except Exception as e:
        logger.error(f"Error exporting orderbook: {str(e)}")
        return Response(content="Error exporting orderbook", status_code=500)


@orders_router.get("/tradebook/export")
@limiter.limit(API_RATE_LIMIT)
async def export_tradebook(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")
        if auth_token is None:
            return RedirectResponse(url="/auth/logout", status_code=302)
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if api_key:
                success, response, status_code = get_tradebook(api_key=api_key)
                if not success:
                    return Response(content="Error getting tradebook data", status_code=500)
                tradebook_data = response.get("data", [])
            else:
                return Response(content="API key required for analyze mode", status_code=400)
        else:
            if not broker:
                return Response(content="Broker not set in session", status_code=400)
            api_funcs = dynamic_import(broker, "api.order_api", ["get_trade_book"])
            mapping_funcs = dynamic_import(broker, "mapping.order_data", ["map_trade_data", "transform_tradebook_data"])
            if not api_funcs or not mapping_funcs:
                return Response(content="Error loading broker-specific modules", status_code=500)
            tradebook_data = api_funcs["get_trade_book"](auth_token)
            if "status" in tradebook_data and tradebook_data["status"] == "error":
                return RedirectResponse(url="/auth/logout", status_code=302)
            tradebook_data = mapping_funcs["map_trade_data"](tradebook_data)
            tradebook_data = mapping_funcs["transform_tradebook_data"](tradebook_data)
        csv_data = generate_tradebook_csv(tradebook_data)
        return Response(content=csv_data, media_type="text/csv",
                       headers={"Content-Disposition": "attachment; filename=tradebook.csv"})
    except Exception as e:
        logger.error(f"Error exporting tradebook: {str(e)}")
        return Response(content="Error exporting tradebook", status_code=500)


@orders_router.get("/positions/export")
@limiter.limit(API_RATE_LIMIT)
async def export_positions(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")
        if auth_token is None:
            return RedirectResponse(url="/auth/logout", status_code=302)
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if api_key:
                success, response, status_code = get_positionbook(api_key=api_key)
                if not success:
                    return Response(content="Error getting positions data", status_code=500)
                positions_data = response.get("data", [])
            else:
                return Response(content="API key required for analyze mode", status_code=400)
        else:
            if not broker:
                return Response(content="Broker not set in session", status_code=400)
            api_funcs = dynamic_import(broker, "api.order_api", ["get_positions"])
            mapping_funcs = dynamic_import(broker, "mapping.order_data", ["map_position_data", "transform_positions_data"])
            if not api_funcs or not mapping_funcs:
                return Response(content="Error loading broker-specific modules", status_code=500)
            positions_data = api_funcs["get_positions"](auth_token)
            if "status" in positions_data and positions_data["status"] == "error":
                return RedirectResponse(url="/auth/logout", status_code=302)
            positions_data = mapping_funcs["map_position_data"](positions_data)
            positions_data = mapping_funcs["transform_positions_data"](positions_data)
        csv_data = generate_positions_csv(positions_data)
        return Response(content=csv_data, media_type="text/csv",
                       headers={"Content-Disposition": "attachment; filename=positions.csv"})
    except Exception as e:
        logger.error(f"Error exporting positions: {str(e)}")
        return Response(content="Error exporting positions", status_code=500)


@orders_router.post("/close_position")
@limiter.limit(API_RATE_LIMIT)
async def close_position(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    try:
        data = await request.json()
        symbol, exchange, product = data.get("symbol"), data.get("exchange"), data.get("product")
        if not all([symbol, exchange, product]):
            return JSONResponse(content={"status": "error", "message": "Missing required parameters"}, status_code=400)
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if not api_key:
                return JSONResponse(content={"status": "error", "message": "API key not found"}, status_code=401)
            order_data = {"strategy": "UI Exit Position", "exchange": exchange, "symbol": symbol, "action": "BUY",
                         "product_type": product, "pricetype": "MARKET", "quantity": "0", "price": "0",
                         "trigger_price": "0", "disclosed_quantity": "0", "position_size": "0"}
            from services.place_smart_order_service import place_smart_order
            success, response_data, status_code = place_smart_order(order_data=order_data, api_key=api_key)
            return JSONResponse(content=response_data, status_code=status_code)
        if not auth_token or not broker_name:
            return JSONResponse(content={"status": "error", "message": "Authentication error"}, status_code=401)
        api_funcs = dynamic_import(broker_name, "api.order_api", ["place_smartorder_api"])
        if not api_funcs:
            return JSONResponse(content={"status": "error", "message": "Error loading broker modules"}, status_code=500)
        order_data = {"strategy": "UI Exit Position", "exchange": exchange, "symbol": symbol, "action": "BUY",
                     "product": product, "pricetype": "MARKET", "quantity": "0", "price": "0",
                     "trigger_price": "0", "disclosed_quantity": "0", "position_size": "0"}
        res, response, orderid = api_funcs["place_smartorder_api"](order_data, auth_token)
        if orderid:
            return JSONResponse(content={"status": "success", "message": "Position close order placed", "orderid": orderid})
        return JSONResponse(content={"status": "error", "message": response.get("message", "Failed to close position") if response else "Failed"}, status_code=400)
    except Exception as e:
        logger.error(f"Error in close_position: {str(e)}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@orders_router.post("/close_all_positions")
@limiter.limit(API_RATE_LIMIT)
async def close_all_positions(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")
        if not auth_token or not broker_name:
            return JSONResponse(content={"status": "error", "message": "Authentication error"}, status_code=401)
        api_key = get_api_key_for_tradingview(login_username) if get_analyze_mode() else None
        success, response_data, status_code = close_position_service(
            position_data={}, api_key=api_key, auth_token=auth_token, broker=broker_name)
        if success and status_code == 200:
            return JSONResponse(content={"status": "success", "message": response_data.get("message", "All positions closed")})
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Error in close_all_positions: {str(e)}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@orders_router.post("/cancel_all_orders")
@limiter.limit(API_RATE_LIMIT)
async def cancel_all_orders_ui(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")
        if not auth_token or not broker_name:
            return JSONResponse(content={"status": "error", "message": "Authentication error"}, status_code=401)
        from services.cancel_all_order_service import cancel_all_orders
        api_key = get_api_key_for_tradingview(login_username) if get_analyze_mode() else None
        success, response_data, status_code = cancel_all_orders(
            order_data={}, api_key=api_key, auth_token=auth_token, broker=broker_name)
        if success and status_code == 200:
            canceled = len(response_data.get("canceled_orders", []))
            failed = len(response_data.get("failed_cancellations", []))
            msg = f"Successfully canceled {canceled} orders" + (f" (Failed: {failed})" if failed else "")
            return JSONResponse(content={"status": "success", "message": msg, "canceled_orders": response_data.get("canceled_orders", [])})
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Error in cancel_all_orders: {str(e)}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@orders_router.post("/cancel_order")
@limiter.limit(API_RATE_LIMIT)
async def cancel_order_ui(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")
        if not auth_token or not broker_name:
            return JSONResponse(content={"status": "error", "message": "Authentication error"}, status_code=401)
        data = await request.json()
        orderid = data.get("orderid")
        if not orderid:
            return JSONResponse(content={"status": "error", "message": "Order ID is required"}, status_code=400)
        from services.cancel_order_service import cancel_order
        api_key = get_api_key_for_tradingview(login_username) if get_analyze_mode() else None
        success, response_data, status_code = cancel_order(
            orderid=orderid, api_key=api_key, auth_token=auth_token, broker=broker_name)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Error in cancel_order: {str(e)}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@orders_router.post("/modify_order")
@limiter.limit(API_RATE_LIMIT)
async def modify_order_ui(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker_name = session.get("broker")
        if not auth_token or not broker_name:
            return JSONResponse(content={"status": "error", "message": "Authentication error"}, status_code=401)
        data = await request.json()
        orderid = data.get("orderid")
        if not orderid:
            return JSONResponse(content={"status": "error", "message": "Order ID is required"}, status_code=400)
        from services.modify_order_service import modify_order
        api_key = get_api_key_for_tradingview(login_username) if get_analyze_mode() else None
        order_data = {"orderid": orderid, "symbol": data.get("symbol"), "exchange": data.get("exchange"),
                     "action": data.get("action"), "product": data.get("product"), "pricetype": data.get("pricetype"),
                     "price": data.get("price"), "quantity": data.get("quantity"),
                     "disclosed_quantity": data.get("disclosed_quantity", 0), "trigger_price": data.get("trigger_price", 0)}
        success, response_data, status_code = modify_order(
            order_data=order_data, api_key=api_key, auth_token=auth_token, broker=broker_name)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Error in modify_order: {str(e)}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@orders_router.get("/action-center")
@limiter.limit(API_RATE_LIMIT)
async def action_center(request: Request, status: str = Query(default="pending"),
                       session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    from services.action_center_service import get_action_center_data
    filter_val = None if status == "all" else status
    success, response, status_code = get_action_center_data(login_username, status_filter=filter_val)
    if not success:
        return JSONResponse(content={"status": "error", "data": {"orders": [], "statistics": {}}}, status_code=status_code)
    return JSONResponse(content={"status": "success", "data": response.get("data", {}), "current_filter": status})


@orders_router.post("/action-center/approve/{order_id}")
@limiter.limit(API_RATE_LIMIT)
async def approve_pending_order_route(request: Request, order_id: int,
                                     session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    from database.action_center_db import approve_pending_order
    from extensions import socketio
    from services.pending_order_execution_service import execute_approved_order
    success = approve_pending_order(order_id, login_username, login_username)
    if success:
        exec_success, response_data, status_code = execute_approved_order(order_id)
        socketio.emit("pending_order_updated", {"action": "approved", "order_id": order_id, "user_id": login_username})
        if exec_success:
            return JSONResponse(content={"status": "success", "message": "Order approved and executed", "broker_order_id": response_data.get("orderid")})
        return JSONResponse(content={"status": "warning", "message": "Approved but execution failed", "error": response_data.get("message")}, status_code=status_code)
    return JSONResponse(content={"status": "error", "message": "Failed to approve order"}, status_code=400)


@orders_router.post("/action-center/reject/{order_id}")
@limiter.limit(API_RATE_LIMIT)
async def reject_pending_order_route(request: Request, order_id: int,
                                    session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    data = await request.json()
    reason = data.get("reason", "No reason provided")
    from database.action_center_db import reject_pending_order
    from extensions import socketio
    success = reject_pending_order(order_id, reason, login_username, login_username)
    if success:
        socketio.emit("pending_order_updated", {"action": "rejected", "order_id": order_id, "user_id": login_username})
        return JSONResponse(content={"status": "success", "message": "Order rejected successfully"})
    return JSONResponse(content={"status": "error", "message": "Failed to reject order"}, status_code=400)


@orders_router.delete("/action-center/delete/{order_id}")
@limiter.limit(API_RATE_LIMIT)
async def delete_pending_order_route(request: Request, order_id: int,
                                    session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    from database.action_center_db import delete_pending_order
    from extensions import socketio
    success = delete_pending_order(order_id, login_username)
    if success:
        socketio.emit("pending_order_updated", {"action": "deleted", "order_id": order_id, "user_id": login_username})
        return JSONResponse(content={"status": "success", "message": "Order deleted successfully"})
    return JSONResponse(content={"status": "error", "message": "Failed to delete order"}, status_code=400)


@orders_router.get("/action-center/count")
async def action_center_count(session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    from database.action_center_db import get_pending_count
    count = get_pending_count(login_username)
    return JSONResponse(content={"count": count})


@orders_router.post("/action-center/approve-all")
@limiter.limit(API_RATE_LIMIT)
async def approve_all_pending_orders(request: Request, session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    from database.action_center_db import approve_pending_order, get_pending_orders
    from extensions import socketio
    from services.pending_order_execution_service import execute_approved_order
    pending_orders = get_pending_orders(login_username, status="pending")
    if not pending_orders:
        return JSONResponse(content={"status": "info", "message": "No pending orders to approve"})
    approved_count, executed_count, failed_executions = 0, 0, []
    for order in pending_orders:
        if approve_pending_order(order.id, login_username, login_username):
            approved_count += 1
            exec_success, response_data, _ = execute_approved_order(order.id)
            if exec_success:
                executed_count += 1
            else:
                failed_executions.append({"order_id": order.id, "error": response_data.get("message", "Unknown")})
    socketio.emit("pending_order_updated", {"action": "batch_approved", "user_id": login_username, "count": approved_count})
    status = "success" if approved_count == executed_count else ("warning" if executed_count > 0 else "error")
    msg = f"Approved {approved_count}, executed {executed_count}" + (f", failed {len(failed_executions)}" if failed_executions else "")
    return JSONResponse(content={"status": status, "message": msg, "approved_count": approved_count,
                                "executed_count": executed_count, "failed_executions": failed_executions})


@orders_router.get("/action-center/api/data")
@limiter.limit(API_RATE_LIMIT)
async def action_center_api_data(request: Request, status: str = Query(default="pending"),
                                session: Dict[str, Any] = Depends(check_session_validity)):
    login_username = session["user"]
    from services.action_center_service import get_action_center_data
    filter_val = None if status == "all" or not status else status
    success, response, status_code = get_action_center_data(login_username, status_filter=filter_val)
    if not success:
        return JSONResponse(content={"status": "error", "message": response.get("message", "Failed"),
                                    "data": {"orders": [], "statistics": {"total_pending": 0, "total_approved": 0,
                                             "total_rejected": 0, "total_buy_orders": 0, "total_sell_orders": 0}}}, status_code=status_code)
    return JSONResponse(content={"status": "success", "data": response.get("data", {})})
