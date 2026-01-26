# routers/broker_credentials.py
"""
FastAPI Broker Credentials Router for RealAlgo
Handles reading and updating broker credentials in the .env file.
Requirements: 4.7
"""

import os
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from dependencies_fastapi import check_session_validity
from utils.logging import get_logger

logger = get_logger(__name__)

broker_credentials_router = APIRouter(prefix="/api/broker", tags=["broker_credentials"])


def get_env_path():
    """Get the absolute path to the .env file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_dir, "..", ".env"))


def read_env_file():
    """Read and parse the .env file into a dictionary of lines."""
    env_path = get_env_path()
    if not os.path.exists(env_path):
        return None, "Environment file not found"

    try:
        with open(env_path, encoding="utf-8") as f:
            return f.read(), None
    except Exception as e:
        logger.error(f"Error reading .env file: {e}")
        return None, str(e)


def update_env_value(content: str, key: str, value: str) -> str:
    """Update a specific key's value in the .env content."""
    pattern = rf"^({re.escape(key)}\s*=\s*).*$"

    if "'" in value:
        escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
        new_value = f'"{escaped_value}"'
    else:
        new_value = f"'{value}'"

    replacement = rf"\g<1>{new_value}"
    new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)

    if count == 0:
        if not new_content.endswith("\n"):
            new_content += "\n"
        new_content += f"{key} = {new_value}\n"

    return new_content


def get_env_value(key: str) -> str:
    """Get a value from the .env file."""
    return os.getenv(key, "")


def mask_secret(value: str, show_chars: int = 4) -> str:
    """Mask a secret value, showing only first few characters."""
    if not value or len(value) <= show_chars:
        return "*" * len(value) if value else ""
    return value[:show_chars] + "*" * (len(value) - show_chars)


def get_broker_from_redirect_url(redirect_url: str) -> str:
    """Extract broker name from redirect URL."""
    try:
        match = re.search(r"/([^/]+)/callback$", redirect_url)
        if match:
            return match.group(1).lower()
    except:
        pass
    return ""


@broker_credentials_router.get("/credentials")
async def get_credentials(request: Request, session: dict = Depends(check_session_validity)):
    """Get current broker credentials (masked)."""
    try:
        broker_api_key = get_env_value("BROKER_API_KEY")
        broker_api_secret = get_env_value("BROKER_API_SECRET")
        broker_api_key_market = get_env_value("BROKER_API_KEY_MARKET")
        broker_api_secret_market = get_env_value("BROKER_API_SECRET_MARKET")
        redirect_url = get_env_value("REDIRECT_URL")
        valid_brokers = get_env_value("VALID_BROKERS")
        ngrok_allow = get_env_value("NGROK_ALLOW")
        host_server = get_env_value("HOST_SERVER")
        websocket_url = get_env_value("WEBSOCKET_URL")

        flask_host = get_env_value("FLASK_HOST_IP") or "127.0.0.1"
        flask_port = get_env_value("FLASK_PORT") or "5000"
        websocket_host = get_env_value("WEBSOCKET_HOST") or "127.0.0.1"
        websocket_port = get_env_value("WEBSOCKET_PORT") or "8765"
        zmq_host = get_env_value("ZMQ_HOST") or "127.0.0.1"
        zmq_port = get_env_value("ZMQ_PORT") or "5555"

        current_broker = get_broker_from_redirect_url(redirect_url)
        brokers_list = [b.strip() for b in valid_brokers.split(",") if b.strip()]

        return JSONResponse({
            "status": "success",
            "data": {
                "broker_api_key": mask_secret(broker_api_key, 6),
                "broker_api_key_raw_length": len(broker_api_key),
                "broker_api_secret": mask_secret(broker_api_secret, 4),
                "broker_api_secret_raw_length": len(broker_api_secret),
                "broker_api_key_market": mask_secret(broker_api_key_market, 6),
                "broker_api_key_market_raw_length": len(broker_api_key_market),
                "broker_api_secret_market": mask_secret(broker_api_secret_market, 4),
                "broker_api_secret_market_raw_length": len(broker_api_secret_market),
                "redirect_url": redirect_url,
                "current_broker": current_broker,
                "valid_brokers": brokers_list,
                "ngrok_allow": ngrok_allow.upper() == "TRUE",
                "host_server": host_server,
                "websocket_url": websocket_url,
                "server_status": {
                    "flask": {"host": flask_host, "port": flask_port},
                    "websocket": {"host": websocket_host, "port": websocket_port},
                    "zmq": {"host": zmq_host, "port": zmq_port},
                },
            },
        })
    except Exception as e:
        logger.error(f"Error getting broker credentials: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@broker_credentials_router.post("/credentials")
async def update_credentials(request: Request, session: dict = Depends(check_session_validity)):
    """Update broker credentials in .env file."""
    try:
        data = await request.json()
        broker_api_key = data.get("broker_api_key", "").strip()
        broker_api_secret = data.get("broker_api_secret", "").strip()
        broker_api_key_market = data.get("broker_api_key_market", "").strip()
        broker_api_secret_market = data.get("broker_api_secret_market", "").strip()
        redirect_url = data.get("redirect_url", "").strip()
        ngrok_allow = data.get("ngrok_allow", "")
        host_server = data.get("host_server", "").strip()
        websocket_url = data.get("websocket_url", "").strip()
        has_ngrok_key = "ngrok_allow" in data

        # Validate redirect URL format
        if redirect_url:
            if not re.match(r"^https?://.+/[^/]+/callback$", redirect_url):
                return JSONResponse(
                    {"status": "error", "message": "Invalid redirect URL format. Must end with /<broker>/callback"},
                    status_code=400,
                )

            broker_name = get_broker_from_redirect_url(redirect_url)
            valid_brokers_str = get_env_value("VALID_BROKERS")
            valid_brokers = set(b.strip().lower() for b in valid_brokers_str.split(",") if b.strip())

            if broker_name and broker_name not in valid_brokers:
                return JSONResponse(
                    {"status": "error", "message": f"Invalid broker '{broker_name}'. Valid brokers: {', '.join(sorted(valid_brokers))}"},
                    status_code=400,
                )

            # Validate broker-specific API key formats
            if broker_name == "fivepaisa" and broker_api_key:
                if ":::" not in broker_api_key or broker_api_key.count(":::") != 2:
                    return JSONResponse(
                        {"status": "error", "message": "5paisa API key must be in format: 'User_Key:::User_ID:::client_id'"},
                        status_code=400,
                    )

            elif broker_name == "flattrade" and broker_api_key:
                if ":::" not in broker_api_key or broker_api_key.count(":::") != 1:
                    return JSONResponse(
                        {"status": "error", "message": "Flattrade API key must be in format: 'client_id:::api_key'"},
                        status_code=400,
                    )

            elif broker_name == "dhan" and broker_api_key:
                if ":::" not in broker_api_key or broker_api_key.count(":::") != 1:
                    return JSONResponse(
                        {"status": "error", "message": "Dhan API key must be in format: 'client_id:::api_key'"},
                        status_code=400,
                    )

        # Read current .env content
        content, error = read_env_file()
        if error:
            return JSONResponse(
                {"status": "error", "message": f"Failed to read .env file: {error}"},
                status_code=500,
            )

        updated_fields = []

        if broker_api_key:
            content = update_env_value(content, "BROKER_API_KEY", broker_api_key)
            updated_fields.append("BROKER_API_KEY")

        if broker_api_secret:
            content = update_env_value(content, "BROKER_API_SECRET", broker_api_secret)
            updated_fields.append("BROKER_API_SECRET")

        if broker_api_key_market:
            content = update_env_value(content, "BROKER_API_KEY_MARKET", broker_api_key_market)
            updated_fields.append("BROKER_API_KEY_MARKET")

        if broker_api_secret_market:
            content = update_env_value(content, "BROKER_API_SECRET_MARKET", broker_api_secret_market)
            updated_fields.append("BROKER_API_SECRET_MARKET")

        if redirect_url:
            content = update_env_value(content, "REDIRECT_URL", redirect_url)
            updated_fields.append("REDIRECT_URL")

        if has_ngrok_key:
            ngrok_allow_str = str(ngrok_allow).strip().upper()
            ngrok_value = "TRUE" if ngrok_allow_str == "TRUE" else "FALSE"
            content = update_env_value(content, "NGROK_ALLOW", ngrok_value)
            updated_fields.append("NGROK_ALLOW")

        if host_server:
            if not re.match(r"^https?://.+", host_server):
                return JSONResponse(
                    {"status": "error", "message": "Invalid HOST_SERVER format. Must start with http:// or https://"},
                    status_code=400,
                )
            content = update_env_value(content, "HOST_SERVER", host_server)
            updated_fields.append("HOST_SERVER")

        if websocket_url:
            if not re.match(r"^wss?://.+", websocket_url):
                return JSONResponse(
                    {"status": "error", "message": "Invalid WEBSOCKET_URL format. Must start with ws:// or wss://"},
                    status_code=400,
                )
            content = update_env_value(content, "WEBSOCKET_URL", websocket_url)
            updated_fields.append("WEBSOCKET_URL")

        if not updated_fields:
            return JSONResponse({"status": "error", "message": "No credentials provided to update"}, status_code=400)

        # Write updated content back to .env
        env_path = get_env_path()
        try:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Updated broker credentials: {', '.join(updated_fields)}")
        except Exception as e:
            logger.error(f"Error writing .env file: {e}")
            return JSONResponse({"status": "error", "message": f"Failed to write .env file: {e}"}, status_code=500)

        return JSONResponse({
            "status": "success",
            "message": f"Credentials updated successfully. Updated: {', '.join(updated_fields)}",
            "updated_fields": updated_fields,
            "restart_required": True,
        })

    except Exception as e:
        logger.error(f"Error updating broker credentials: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
