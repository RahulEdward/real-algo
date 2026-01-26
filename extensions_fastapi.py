# extensions_fastapi.py
"""
FastAPI Socket.IO Extensions for RealAlgo

This module provides Socket.IO configuration for FastAPI using python-socketio
with ASGI mode. It replaces Flask-SocketIO with an async-compatible implementation.

Requirements: 6.1 (WebSocket Migration)
"""

import time

import socketio

from utils.logging import get_logger

logger = get_logger(__name__)

# Create AsyncServer for ASGI mode
# This replaces Flask-SocketIO's SocketIO instance
# 
# Configuration matches Flask-SocketIO settings:
# - cors_allowed_origins="*" - Allow all origins (same as Flask)
# - async_mode="asgi" - Use ASGI mode for FastAPI compatibility
# - ping_timeout=10 - Time in seconds before considering connection lost
# - ping_interval=5 - Interval in seconds between pings
# - logger=False - Disable built-in logging to avoid noise
# - engineio_logger=False - Disable engine.io logging
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    ping_timeout=10,
    ping_interval=5,
    logger=False,
    engineio_logger=False,
)

# Create ASGI app wrapper for mounting on FastAPI
# This will be mounted at /socket.io in app_fastapi.py
socket_app = socketio.ASGIApp(
    sio,
    # socketio_path is the path within the mount point
    # Since we mount at /socket.io, the full path will be /socket.io/socket.io
    # But clients connect to /socket.io which is the standard
    socketio_path="",
)

# Track Socket.IO subscriber IDs per session (mirrors Flask version)
socketio_subscribers = {}


# ============================================================
# Default Namespace Event Handlers
# These handle connections to the root namespace "/"
# ============================================================


@sio.event
async def connect(sid, environ, auth=None):
    """
    Handle client connection to default namespace.
    
    Args:
        sid: Session ID for the connected client
        environ: WSGI/ASGI environ dict with connection info
        auth: Optional authentication data from client
    """
    logger.debug(f"Client connected: {sid}")
    
    # Store connection info in session
    await sio.save_session(sid, {
        "connected": True,
        "subscriptions": [],
    })
    
    # Emit connection acknowledgment
    await sio.emit("connected", {"sid": sid}, to=sid)


@sio.event
async def disconnect(sid):
    """
    Handle client disconnection from default namespace.
    
    Args:
        sid: Session ID of the disconnected client
    """
    logger.debug(f"Client disconnected: {sid}")
    
    # Clean up any subscriptions
    try:
        session = await sio.get_session(sid)
        subscriptions = session.get("subscriptions", [])
        if subscriptions:
            logger.debug(f"Cleaning up {len(subscriptions)} subscriptions for {sid}")
    except Exception as e:
        logger.debug(f"Error cleaning up session for {sid}: {e}")


@sio.event
async def subscribe(sid, data):
    """
    Handle subscription requests for market data (default namespace).
    
    Args:
        sid: Session ID of the client
        data: Subscription data containing symbols and mode
    """
    try:
        session = await sio.get_session(sid)
        subscriptions = session.get("subscriptions", [])
        
        # Add new subscription
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        mode = data.get("mode", "LTP")
        
        if symbol and exchange:
            subscription = {
                "symbol": symbol,
                "exchange": exchange,
                "mode": mode,
            }
            if subscription not in subscriptions:
                subscriptions.append(subscription)
                await sio.save_session(sid, {**session, "subscriptions": subscriptions})
                logger.debug(f"Client {sid} subscribed to {symbol}@{exchange} ({mode})")
                
                # Acknowledge subscription
                await sio.emit("subscribed", subscription, to=sid)
        else:
            await sio.emit("error", {"message": "Invalid subscription data"}, to=sid)
            
    except Exception as e:
        logger.error(f"Error handling subscription for {sid}: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid)


@sio.event
async def unsubscribe(sid, data):
    """
    Handle unsubscription requests (default namespace).
    
    Args:
        sid: Session ID of the client
        data: Unsubscription data containing symbol and exchange
    """
    try:
        session = await sio.get_session(sid)
        subscriptions = session.get("subscriptions", [])
        
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        
        if symbol and exchange:
            # Remove matching subscriptions
            subscriptions = [
                s for s in subscriptions
                if not (s.get("symbol") == symbol and s.get("exchange") == exchange)
            ]
            await sio.save_session(sid, {**session, "subscriptions": subscriptions})
            logger.debug(f"Client {sid} unsubscribed from {symbol}@{exchange}")
            
            # Acknowledge unsubscription
            await sio.emit("unsubscribed", {"symbol": symbol, "exchange": exchange}, to=sid)
            
    except Exception as e:
        logger.error(f"Error handling unsubscription for {sid}: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid)


@sio.event
async def ping_server(sid, data=None):
    """
    Handle ping requests from clients.
    Used for connection health checks.
    
    Args:
        sid: Session ID of the client
        data: Optional ping data
    """
    await sio.emit("pong_server", {"status": "ok"}, to=sid)


# ============================================================
# /market Namespace Event Handlers
# These mirror Flask-SocketIO handlers from websocket_example.py
# ============================================================


@sio.on("connect", namespace="/market")
async def handle_market_connect(sid, environ, auth=None):
    """
    Handle client connection to /market namespace.
    Supports API key authentication via auth parameter or query string.
    
    Args:
        sid: Session ID for the connected client
        environ: WSGI/ASGI environ dict with connection info
        auth: Optional authentication data from client (can contain api_key)
    """
    logger.info(f"Client {sid} connecting to /market namespace")
    
    # Extract API key from auth data or query string
    api_key = None
    username = None
    
    # Try to get API key from auth parameter (Socket.IO auth)
    if auth and isinstance(auth, dict):
        api_key = auth.get("api_key") or auth.get("apikey")
    
    # Try to get API key from query string
    if not api_key:
        query_string = environ.get("QUERY_STRING", "")
        if query_string:
            from urllib.parse import parse_qs
            params = parse_qs(query_string)
            api_key = params.get("api_key", [None])[0] or params.get("apikey", [None])[0]
    
    # Verify API key if provided
    if api_key:
        try:
            from database.auth_db import verify_api_key, get_broker_name
            
            user_id = verify_api_key(api_key)
            if user_id:
                username = user_id
                broker_name = get_broker_name(api_key)
                logger.info(f"Client {sid} authenticated as user {username} with broker {broker_name}")
            else:
                logger.warning(f"Client {sid} provided invalid API key")
                # Don't reject - allow connection but mark as unauthenticated
        except Exception as e:
            logger.error(f"Error verifying API key for {sid}: {e}")
    
    # Store session info
    await sio.save_session(sid, {
        "connected": True,
        "namespace": "/market",
        "subscriptions": [],
        "username": username,
        "authenticated": username is not None,
    }, namespace="/market")
    
    # Join user-specific room if authenticated
    if username:
        sio.enter_room(sid, f"user_{username}", namespace="/market")
    
    # Emit connection acknowledgment
    await sio.emit(
        "connected",
        {
            "status": "Connected to market data stream",
            "authenticated": username is not None,
            "username": username,
        },
        to=sid,
        namespace="/market"
    )


@sio.on("disconnect", namespace="/market")
async def handle_market_disconnect(sid):
    """
    Handle client disconnection from /market namespace.
    
    Args:
        sid: Session ID of the disconnected client
    """
    try:
        session = await sio.get_session(sid, namespace="/market")
        username = session.get("username")
        if username:
            sio.leave_room(sid, f"user_{username}", namespace="/market")
            logger.info(f"User {username} (client {sid}) disconnected from /market namespace")
        else:
            logger.info(f"Client {sid} disconnected from /market namespace")
    except Exception as e:
        logger.debug(f"Error during disconnect cleanup for {sid}: {e}")
    
    # Clean up subscriber tracking
    if sid in socketio_subscribers:
        del socketio_subscribers[sid]


@sio.on("authenticate", namespace="/market")
async def handle_market_authenticate(sid, data):
    """
    Handle explicit authentication request on /market namespace.
    This allows clients to authenticate after connection.
    
    Args:
        sid: Session ID of the client
        data: Authentication data containing api_key
    """
    try:
        from database.auth_db import verify_api_key, get_broker_name
        
        api_key = data.get("api_key") or data.get("apikey")
        
        if not api_key:
            await sio.emit(
                "auth_error",
                {"status": "error", "message": "API key is required"},
                to=sid,
                namespace="/market"
            )
            return
        
        user_id = verify_api_key(api_key)
        
        if not user_id:
            await sio.emit(
                "auth_error",
                {"status": "error", "message": "Invalid API key"},
                to=sid,
                namespace="/market"
            )
            return
        
        broker_name = get_broker_name(api_key)
        
        # Update session with authentication info
        session = await sio.get_session(sid, namespace="/market")
        session["username"] = user_id
        session["authenticated"] = True
        session["broker"] = broker_name
        await sio.save_session(sid, session, namespace="/market")
        
        # Join user-specific room
        sio.enter_room(sid, f"user_{user_id}", namespace="/market")
        
        logger.info(f"Client {sid} authenticated as user {user_id} with broker {broker_name}")
        
        await sio.emit(
            "auth_success",
            {
                "status": "success",
                "message": "Authentication successful",
                "username": user_id,
                "broker": broker_name,
            },
            to=sid,
            namespace="/market"
        )
        
    except Exception as e:
        logger.error(f"Error handling authentication for {sid}: {e}")
        await sio.emit(
            "auth_error",
            {"status": "error", "message": str(e)},
            to=sid,
            namespace="/market"
        )


@sio.on("subscribe", namespace="/market")
async def handle_market_subscribe(sid, data):
    """
    Handle subscription request via Socket.IO on /market namespace.
    
    Args:
        sid: Session ID of the client
        data: Subscription data with symbols, mode, and optional broker
    """
    try:
        from services.websocket_service import subscribe_to_symbols
        
        symbols = data.get("symbols", [])
        mode = data.get("mode", "Quote")
        broker = data.get("broker")
        
        # Get username from session or auth data
        session = await sio.get_session(sid, namespace="/market")
        username = session.get("username") or data.get("username")
        
        if not username:
            await sio.emit(
                "error",
                {"message": "Not authenticated"},
                to=sid,
                namespace="/market"
            )
            return
        
        success, result, _ = subscribe_to_symbols(username, broker, symbols, mode)
        
        if success:
            await sio.emit("subscription_success", result, to=sid, namespace="/market")
        else:
            await sio.emit("subscription_error", result, to=sid, namespace="/market")
            
    except Exception as e:
        logger.error(f"Error handling /market subscribe for {sid}: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid, namespace="/market")


@sio.on("unsubscribe", namespace="/market")
async def handle_market_unsubscribe(sid, data):
    """
    Handle unsubscription request via Socket.IO on /market namespace.
    
    Args:
        sid: Session ID of the client
        data: Unsubscription data with symbols, mode, and optional broker
    """
    try:
        from services.websocket_service import unsubscribe_from_symbols
        
        symbols = data.get("symbols", [])
        mode = data.get("mode", "Quote")
        broker = data.get("broker")
        
        # Get username from session or auth data
        session = await sio.get_session(sid, namespace="/market")
        username = session.get("username") or data.get("username")
        
        if not username:
            await sio.emit(
                "error",
                {"message": "Not authenticated"},
                to=sid,
                namespace="/market"
            )
            return
        
        success, result, _ = unsubscribe_from_symbols(username, broker, symbols, mode)
        
        if success:
            await sio.emit("unsubscription_success", result, to=sid, namespace="/market")
        else:
            await sio.emit("unsubscription_error", result, to=sid, namespace="/market")
            
    except Exception as e:
        logger.error(f"Error handling /market unsubscribe for {sid}: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid, namespace="/market")


@sio.on("get_ltp", namespace="/market")
async def handle_get_ltp(sid, data):
    """
    Get LTP for a symbol on /market namespace.
    
    Args:
        sid: Session ID of the client
        data: Request data with symbol and exchange
    """
    try:
        from services.market_data_service import get_market_data_service
        
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        
        if not symbol or not exchange:
            await sio.emit(
                "error",
                {"message": "Symbol and exchange are required"},
                to=sid,
                namespace="/market"
            )
            return
        
        market_service = get_market_data_service()
        ltp_data = market_service.get_ltp(symbol, exchange)
        
        await sio.emit(
            "ltp_data",
            {"symbol": symbol, "exchange": exchange, "data": ltp_data},
            to=sid,
            namespace="/market"
        )
        
    except Exception as e:
        logger.error(f"Error handling get_ltp for {sid}: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid, namespace="/market")


@sio.on("get_quote", namespace="/market")
async def handle_get_quote(sid, data):
    """
    Get quote for a symbol on /market namespace.
    
    Args:
        sid: Session ID of the client
        data: Request data with symbol and exchange
    """
    try:
        from services.market_data_service import get_market_data_service
        
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        
        if not symbol or not exchange:
            await sio.emit(
                "error",
                {"message": "Symbol and exchange are required"},
                to=sid,
                namespace="/market"
            )
            return
        
        market_service = get_market_data_service()
        quote_data = market_service.get_quote(symbol, exchange)
        
        await sio.emit(
            "quote_data",
            {"symbol": symbol, "exchange": exchange, "data": quote_data},
            to=sid,
            namespace="/market"
        )
        
    except Exception as e:
        logger.error(f"Error handling get_quote for {sid}: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid, namespace="/market")


@sio.on("get_depth", namespace="/market")
async def handle_get_depth(sid, data):
    """
    Get market depth for a symbol on /market namespace.
    
    Args:
        sid: Session ID of the client
        data: Request data with symbol and exchange
    """
    try:
        from services.market_data_service import get_market_data_service
        
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        
        if not symbol or not exchange:
            await sio.emit(
                "error",
                {"message": "Symbol and exchange are required"},
                to=sid,
                namespace="/market"
            )
            return
        
        market_service = get_market_data_service()
        depth_data = market_service.get_market_depth(symbol, exchange)
        
        await sio.emit(
            "depth_data",
            {"symbol": symbol, "exchange": exchange, "data": depth_data},
            to=sid,
            namespace="/market"
        )
        
    except Exception as e:
        logger.error(f"Error handling get_depth for {sid}: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid, namespace="/market")


# ============================================================
# Broadcast Functions
# These are used by services to broadcast market data
# ============================================================


async def broadcast_market_data(data: dict, room: str = None):
    """
    Broadcast market data to all connected clients or a specific room.
    
    Args:
        data: Market data to broadcast
        room: Optional room name to broadcast to
    """
    try:
        if room:
            await sio.emit("market_data", data, room=room)
        else:
            await sio.emit("market_data", data)
    except Exception as e:
        logger.error(f"Error broadcasting market data: {e}")


async def broadcast_order_update(data: dict, sid: str = None):
    """
    Broadcast order update to a specific client or all clients.
    
    Args:
        data: Order update data
        sid: Optional session ID to send to specific client
    """
    try:
        if sid:
            await sio.emit("order_update", data, to=sid)
        else:
            await sio.emit("order_update", data)
    except Exception as e:
        logger.error(f"Error broadcasting order update: {e}")


async def broadcast_position_update(data: dict, sid: str = None):
    """
    Broadcast position update to a specific client or all clients.
    
    Args:
        data: Position update data
        sid: Optional session ID to send to specific client
    """
    try:
        if sid:
            await sio.emit("position_update", data, to=sid)
        else:
            await sio.emit("position_update", data)
    except Exception as e:
        logger.error(f"Error broadcasting position update: {e}")


# ============================================================
# Room Management
# ============================================================


async def join_room(sid: str, room: str):
    """
    Add a client to a room for targeted broadcasts.
    
    Args:
        sid: Session ID of the client
        room: Room name to join
    """
    sio.enter_room(sid, room)
    logger.debug(f"Client {sid} joined room {room}")


async def leave_room(sid: str, room: str):
    """
    Remove a client from a room.
    
    Args:
        sid: Session ID of the client
        room: Room name to leave
    """
    sio.leave_room(sid, room)
    logger.debug(f"Client {sid} left room {room}")


# ============================================================
# Utility Functions
# ============================================================


def get_connected_clients() -> int:
    """
    Get the number of connected clients.
    
    Returns:
        Number of connected clients
    """
    # In async mode, we need to track this differently
    # For now, return the number of rooms (each client has their own room)
    return len(sio.manager.rooms.get("/", {}).keys()) - 1  # Subtract 1 for the default room


async def emit_to_client(event: str, data: dict, sid: str):
    """
    Emit an event to a specific client.
    
    Args:
        event: Event name
        data: Event data
        sid: Session ID of the target client
    """
    await sio.emit(event, data, to=sid)


async def emit_to_all(event: str, data: dict):
    """
    Emit an event to all connected clients.
    
    Args:
        event: Event name
        data: Event data
    """
    await sio.emit(event, data)



# ============================================================
# Broadcast Functions
# These are used by services to broadcast market data
# ============================================================


async def broadcast_market_data(data: dict, room: str = None, namespace: str = None):
    """
    Broadcast market data to all connected clients or a specific room.
    
    Args:
        data: Market data to broadcast
        room: Optional room name to broadcast to
        namespace: Optional namespace (default: None for root, "/market" for market)
    """
    try:
        if room:
            await sio.emit("market_data", data, room=room, namespace=namespace)
        else:
            await sio.emit("market_data", data, namespace=namespace)
    except Exception as e:
        logger.error(f"Error broadcasting market data: {e}")


async def broadcast_ltp_update(symbol: str, exchange: str, ltp: float, namespace: str = "/market"):
    """
    Broadcast LTP update to all subscribed clients.
    
    Args:
        symbol: Symbol name
        exchange: Exchange name
        ltp: Last traded price
        namespace: Namespace to broadcast to
    """
    try:
        data = {
            "type": "ltp",
            "symbol": symbol,
            "exchange": exchange,
            "ltp": ltp,
            "timestamp": int(time.time() * 1000),
        }
        await sio.emit("ltp_update", data, namespace=namespace)
    except Exception as e:
        logger.error(f"Error broadcasting LTP update: {e}")


async def broadcast_quote_update(symbol: str, exchange: str, quote_data: dict, namespace: str = "/market"):
    """
    Broadcast quote update to all subscribed clients.
    
    Args:
        symbol: Symbol name
        exchange: Exchange name
        quote_data: Quote data dictionary
        namespace: Namespace to broadcast to
    """
    try:
        data = {
            "type": "quote",
            "symbol": symbol,
            "exchange": exchange,
            "data": quote_data,
            "timestamp": int(time.time() * 1000),
        }
        await sio.emit("quote_update", data, namespace=namespace)
    except Exception as e:
        logger.error(f"Error broadcasting quote update: {e}")


async def broadcast_depth_update(symbol: str, exchange: str, depth_data: dict, namespace: str = "/market"):
    """
    Broadcast market depth update to all subscribed clients.
    
    Args:
        symbol: Symbol name
        exchange: Exchange name
        depth_data: Market depth data dictionary
        namespace: Namespace to broadcast to
    """
    try:
        data = {
            "type": "depth",
            "symbol": symbol,
            "exchange": exchange,
            "data": depth_data,
            "timestamp": int(time.time() * 1000),
        }
        await sio.emit("depth_update", data, namespace=namespace)
    except Exception as e:
        logger.error(f"Error broadcasting depth update: {e}")


async def broadcast_order_update(data: dict, sid: str = None, namespace: str = None):
    """
    Broadcast order update to a specific client or all clients.
    
    Args:
        data: Order update data
        sid: Optional session ID to send to specific client
        namespace: Optional namespace
    """
    try:
        if sid:
            await sio.emit("order_update", data, to=sid, namespace=namespace)
        else:
            await sio.emit("order_update", data, namespace=namespace)
    except Exception as e:
        logger.error(f"Error broadcasting order update: {e}")


async def broadcast_position_update(data: dict, sid: str = None, namespace: str = None):
    """
    Broadcast position update to a specific client or all clients.
    
    Args:
        data: Position update data
        sid: Optional session ID to send to specific client
        namespace: Optional namespace
    """
    try:
        if sid:
            await sio.emit("position_update", data, to=sid, namespace=namespace)
        else:
            await sio.emit("position_update", data, namespace=namespace)
    except Exception as e:
        logger.error(f"Error broadcasting position update: {e}")


async def broadcast_to_user(username: str, event: str, data: dict, namespace: str = "/market"):
    """
    Broadcast an event to a specific user's room.
    
    Args:
        username: Username to broadcast to
        event: Event name
        data: Event data
        namespace: Namespace (default: /market)
    """
    try:
        room = f"user_{username}"
        await sio.emit(event, data, room=room, namespace=namespace)
    except Exception as e:
        logger.error(f"Error broadcasting to user {username}: {e}")


# ============================================================
# Room Management
# ============================================================


async def join_room(sid: str, room: str, namespace: str = None):
    """
    Add a client to a room for targeted broadcasts.
    
    Args:
        sid: Session ID of the client
        room: Room name to join
        namespace: Optional namespace
    """
    sio.enter_room(sid, room, namespace=namespace)
    logger.debug(f"Client {sid} joined room {room}")


async def leave_room(sid: str, room: str, namespace: str = None):
    """
    Remove a client from a room.
    
    Args:
        sid: Session ID of the client
        room: Room name to leave
        namespace: Optional namespace
    """
    sio.leave_room(sid, room, namespace=namespace)
    logger.debug(f"Client {sid} left room {room}")


# ============================================================
# Utility Functions
# ============================================================


def get_connected_clients(namespace: str = None) -> int:
    """
    Get the number of connected clients.
    
    Args:
        namespace: Optional namespace to count clients for
    
    Returns:
        Number of connected clients
    """
    try:
        ns = namespace or "/"
        rooms = sio.manager.rooms.get(ns, {})
        # Each client has their own room (sid), plus any custom rooms
        # Count unique sids
        return len(rooms.keys()) - 1 if rooms else 0  # Subtract 1 for the default room
    except Exception:
        return 0


async def emit_to_client(event: str, data: dict, sid: str, namespace: str = None):
    """
    Emit an event to a specific client.
    
    Args:
        event: Event name
        data: Event data
        sid: Session ID of the target client
        namespace: Optional namespace
    """
    await sio.emit(event, data, to=sid, namespace=namespace)


async def emit_to_all(event: str, data: dict, namespace: str = None):
    """
    Emit an event to all connected clients.
    
    Args:
        event: Event name
        data: Event data
        namespace: Optional namespace
    """
    await sio.emit(event, data, namespace=namespace)


async def emit_to_room(event: str, data: dict, room: str, namespace: str = None):
    """
    Emit an event to all clients in a room.
    
    Args:
        event: Event name
        data: Event data
        room: Room name
        namespace: Optional namespace
    """
    await sio.emit(event, data, room=room, namespace=namespace)


async def get_client_session(sid: str, namespace: str = None) -> dict:
    """
    Get session data for a client.
    
    Args:
        sid: Session ID of the client
        namespace: Optional namespace
    
    Returns:
        Session data dictionary
    """
    try:
        return await sio.get_session(sid, namespace=namespace)
    except Exception:
        return {}


async def save_client_session(sid: str, data: dict, namespace: str = None):
    """
    Save session data for a client.
    
    Args:
        sid: Session ID of the client
        data: Session data to save
        namespace: Optional namespace
    """
    await sio.save_session(sid, data, namespace=namespace)
