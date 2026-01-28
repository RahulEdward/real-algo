# utils/plugin_loader.py

import importlib
import os
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


def load_broker_auth_functions(broker_directory="broker"):
    """
    Load broker authentication functions from broker plugins.
    
    Args:
        broker_directory: Directory containing broker plugins (default: "broker")
        
    Returns:
        Dict mapping broker auth function names to their functions
    """
    auth_functions = {}
    
    # Get the broker path relative to this file's location
    root_path = Path(__file__).parent.parent
    broker_path = root_path / broker_directory
    
    if not broker_path.exists():
        logger.warning(f"Broker directory not found: {broker_path}")
        return auth_functions
    
    # List all items in broker directory and filter out __pycache__ and non-directories
    broker_names = [
        d.name
        for d in broker_path.iterdir()
        if d.is_dir() and d.name != "__pycache__"
    ]

    for broker_name in broker_names:
        try:
            # Construct module name and import the module
            module_name = f"{broker_directory}.{broker_name}.api.auth_api"
            auth_module = importlib.import_module(module_name)
            # Retrieve the authenticate_broker function
            auth_function = getattr(auth_module, "authenticate_broker", None)
            if auth_function:
                auth_functions[f"{broker_name}_auth"] = auth_function
        except ImportError as e:
            logger.error(f"Failed to import broker plugin {broker_name}: {e}")
        except AttributeError as e:
            logger.error(f"Authentication function not found in broker plugin {broker_name}: {e}")

    return auth_functions
