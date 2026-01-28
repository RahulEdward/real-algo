# extensions.py
"""
Socket.IO Extensions for RealAlgo

This module provides a compatibility layer for Socket.IO.
It exports a socketio object that can be used by broker modules
for emitting events during master contract download.

For FastAPI, this wraps the async socketio from extensions_fastapi.py
with a synchronous interface for backward compatibility.
"""

import asyncio
from typing import Any, Dict, Optional

from utils.logging import get_logger

logger = get_logger(__name__)


class SyncSocketIOWrapper:
    """
    Synchronous wrapper around async Socket.IO for backward compatibility.
    
    This allows broker modules (which run in threads) to emit events
    without needing to handle async code.
    """
    
    def __init__(self):
        self._sio = None
        self._loop = None
    
    def _get_sio(self):
        """Lazy load the async socketio instance."""
        if self._sio is None:
            try:
                from extensions_fastapi import sio
                self._sio = sio
            except ImportError:
                logger.warning("extensions_fastapi not available, socketio emit will be no-op")
        return self._sio
    
    def emit(self, event: str, data: Dict[str, Any] = None, namespace: str = None, room: str = None, to: str = None) -> bool:
        """
        Emit a Socket.IO event synchronously.
        
        This is a compatibility wrapper that handles the async nature of
        python-socketio when called from synchronous code (like broker threads).
        
        Args:
            event: Event name to emit
            data: Data to send with the event
            namespace: Optional namespace
            room: Optional room to emit to
            to: Optional specific client to emit to
            
        Returns:
            True if emit was successful, False otherwise
        """
        logger.info(f"SyncSocketIOWrapper.emit called: event={event}, data={data}")
        sio = self._get_sio()
        if sio is None:
            logger.warning(f"Socket.IO not available, skipping emit for event: {event}")
            return False
        
        try:
            # Try to get the running event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, schedule the emit
                asyncio.create_task(self._async_emit(sio, event, data, namespace, room, to))
                return True
            except RuntimeError:
                # No running loop, we're in a sync context (like a thread)
                # Create a new loop for this emit
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._async_emit(sio, event, data, namespace, room, to))
                    return True
                finally:
                    loop.close()
                    
        except Exception as e:
            logger.error(f"Error emitting Socket.IO event {event}: {e}")
            return False
    
    async def _async_emit(self, sio, event: str, data: Dict[str, Any], namespace: str, room: str, to: str):
        """Async emit helper."""
        try:
            kwargs = {}
            if namespace:
                kwargs["namespace"] = namespace
            if room:
                kwargs["room"] = room
            if to:
                kwargs["to"] = to
            
            await sio.emit(event, data, **kwargs)
            logger.debug(f"Emitted Socket.IO event: {event}")
        except Exception as e:
            logger.error(f"Error in async emit for {event}: {e}")


# Create the global socketio instance
# This is used by broker modules for backward compatibility
socketio = SyncSocketIOWrapper()
