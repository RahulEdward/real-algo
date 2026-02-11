"""
Session compatibility layer for broker modules.

Broker modules use `from flask import session` to access session data
like USER_ID, username, etc. Since we've migrated to FastAPI/Starlette,
Flask's session is no longer available.

This module provides a thread-local session proxy that mimics Flask's
session interface. The session data is populated from Starlette's session
before broker functions are called (in auth_utils_fastapi.py).

Usage in broker files:
    Replace: from flask import session
    With:    from utils.session_compat import session
"""

import threading
from typing import Any, Optional

from utils.logging import get_logger

logger = get_logger(__name__)


class ThreadLocalSession:
    """
    Thread-local session proxy that mimics Flask's session interface.
    
    Each thread gets its own session data dict. This is safe because
    broker operations run in dedicated threads.
    """

    def __init__(self):
        self._local = threading.local()

    def _get_data(self) -> dict:
        if not hasattr(self._local, "data"):
            self._local.data = {}
        return self._local.data

    def get(self, key: str, default: Any = None) -> Any:
        return self._get_data().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._get_data()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._get_data()[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._get_data()

    def __delitem__(self, key: str) -> None:
        data = self._get_data()
        if key in data:
            del data[key]

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"ThreadLocalSession({self._get_data()})"

    def clear(self) -> None:
        self._get_data().clear()

    def update(self, data: dict) -> None:
        """Update session with data from Starlette session."""
        self._get_data().update(data)

    def pop(self, key: str, *args) -> Any:
        return self._get_data().pop(key, *args)

    def keys(self):
        return self._get_data().keys()

    def values(self):
        return self._get_data().values()

    def items(self):
        return self._get_data().items()

    # Support hasattr checks like hasattr(session, "marketdata_userid")
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._get_data().get(name)


# Global session proxy - broker modules import this
session = ThreadLocalSession()


def populate_session_for_thread(session_data: dict) -> None:
    """
    Populate the thread-local session with data from Starlette session.
    
    Call this before invoking broker functions in a thread.
    
    Args:
        session_data: Dict of session data to copy into thread-local storage.
    """
    session.clear()
    session.update(session_data)
    logger.debug(f"Thread-local session populated with keys: {list(session_data.keys())}")
