"""
Socket.IO Error Handler
Handles common Socket.IO errors like disconnected sessions gracefully

This module works with python-socketio (ASGI mode) for FastAPI.
"""

import functools
from typing import Callable

from utils.logging import get_logger

logger = get_logger(__name__)


def handle_disconnected_session(f: Callable) -> Callable:
    """
    Decorator to handle disconnected session errors in Socket.IO event handlers.
    
    Works with python-socketio AsyncServer.
    """

    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except KeyError as e:
            if str(e) == "'Session is disconnected'":
                logger.debug(f"Socket.IO session already disconnected in {f.__name__}")
                return None
            raise
        except Exception as e:
            if "Session is disconnected" in str(e):
                logger.debug(f"Socket.IO session disconnected in {f.__name__}: {e}")
                return None
            raise

    return wrapper


def init_socketio_error_handling(sio):
    """
    Initialize Socket.IO error handling for python-socketio AsyncServer.

    Args:
        sio: The python-socketio AsyncServer instance
    """
    
    # python-socketio doesn't have on_error_default like Flask-SocketIO
    # Error handling is done through try/except in event handlers
    # or by setting up a custom error handler
    
    logger.debug("Socket.IO error handling initialized for python-socketio")
