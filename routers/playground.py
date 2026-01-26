# routers/playground.py
"""
FastAPI Playground Router for RealAlgo
Handles API playground for testing broker API endpoints.
Requirements: 4.7
"""

import glob
import json
import os
import re
from collections import OrderedDict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from database.auth_db import get_api_key_for_tradingview
from dependencies_fastapi import check_session_validity, get_session
from limiter_fastapi import limiter
from utils.logging import get_logger

logger = get_logger(__name__)

API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "50/second")

playground_router = APIRouter(prefix="/playground", tags=["playground"])
templates = Jinja2Templates(directory="templates")


def parse_bru_file(filepath):
    """Parse a Bruno .bru file and extract endpoint information"""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        endpoint = {}

        # Extract meta block
        meta_match = re.search(r"meta\s*\{([^}]+)\}", content)
        if meta_match:
            meta_content = meta_match.group(1)
            name_match = re.search(r"name:\s*(.+)", meta_content)
            seq_match = re.search(r"seq:\s*(\d+)", meta_content)
            type_match = re.search(r"type:\s*(.+)", meta_content)
            if name_match:
                endpoint["name"] = name_match.group(1).strip()
            if seq_match:
                endpoint["seq"] = int(seq_match.group(1).strip())
            if type_match:
                endpoint["type"] = type_match.group(1).strip()

        # Check if this is a WebSocket endpoint
        if endpoint.get("type") == "websocket":
            ws_match = re.search(r"websocket\s*\{([^}]+)\}", content)
            if ws_match:
                ws_content = ws_match.group(1)
                url_match = re.search(r"url:\s*(.+)", ws_content)
                desc_match = re.search(r"description:\s*(.+)", ws_content)
                if url_match:
                    endpoint["path"] = url_match.group(1).strip()
                if desc_match:
                    endpoint["description"] = desc_match.group(1).strip()
                endpoint["method"] = "WS"

            message_start = content.find("message:json")
            if message_start != -1:
                brace_start = content.find("{", message_start)
                if brace_start != -1:
                    depth = 0
                    body_end = brace_start
                    for i, char in enumerate(content[brace_start:], start=brace_start):
                        if char == "{":
                            depth += 1
                        elif char == "}":
                            depth -= 1
                            if depth == 0:
                                body_end = i
                                break
                    body_content = content[brace_start + 1 : body_end].strip()
                    try:
                        body_json = json.loads(body_content, object_pairs_hook=OrderedDict)
                        endpoint["body"] = body_json
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON message in {filepath}")

            return endpoint if "name" in endpoint else None

        # Extract HTTP method and URL
        method_match = re.search(
            r"(get|post|put|delete|patch)\s*\{([^}]+)\}", content, re.IGNORECASE
        )
        if method_match:
            endpoint["method"] = method_match.group(1).upper()
            method_content = method_match.group(2)
            url_match = re.search(r"url:\s*(.+)", method_content)
            if url_match:
                full_url = url_match.group(1).strip()
                path_match = re.search(r"(/api/v1/[^?]+)", full_url)
                if path_match:
                    endpoint["path"] = path_match.group(1)

                if endpoint.get("method") == "GET":
                    query_match = re.search(r"\?(.+)$", full_url)
                    if query_match:
                        query_string = query_match.group(1)
                        params = {}
                        for param in query_string.split("&"):
                            if "=" in param:
                                key, value = param.split("=", 1)
                                if key == "apikey":
                                    params[key] = ""
                                else:
                                    params[key] = value
                        if params:
                            endpoint["params"] = params

        # Extract body:json block
        body_start = content.find("body:json")
        if body_start != -1:
            brace_start = content.find("{", body_start)
            if brace_start != -1:
                depth = 0
                body_end = brace_start
                for i, char in enumerate(content[brace_start:], start=brace_start):
                    if char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            body_end = i
                            break

                body_content = content[brace_start + 1 : body_end].strip()
                try:
                    body_json = json.loads(body_content, object_pairs_hook=OrderedDict)
                    if isinstance(body_json, (dict, OrderedDict)) and "apikey" in body_json:
                        body_json["apikey"] = ""
                    endpoint["body"] = body_json
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON body in {filepath}")

        # Extract query params
        params_match = re.search(r"params:query\s*\{([^}]+)\}", content)
        if params_match:
            params = {}
            params_content = params_match.group(1)
            for line in params_content.split("\n"):
                param_match = re.search(r"(\w+):\s*(.+)", line)
                if param_match:
                    key = param_match.group(1).strip()
                    value = param_match.group(2).strip()
                    params[key] = value
            if params:
                endpoint["params"] = params

        return endpoint if "name" in endpoint and "path" in endpoint else None

    except Exception as e:
        logger.error(f"Error parsing Bruno file {filepath}: {e}")
        return None


def categorize_endpoint(path):
    """Categorize an endpoint based on its path"""
    path_lower = path.lower()

    if any(
        x in path_lower
        for x in ["/funds", "/orderbook", "/tradebook", "/positionbook", "/holdings", "/analyzer", "/margin"]
    ):
        return "account"

    if any(
        x in path_lower
        for x in [
            "/placeorder", "/placesmartorder", "/optionsorder", "/optionsmultiorder",
            "/basketorder", "/splitorder", "/modifyorder", "/cancelorder", "/cancelallorder",
            "/closeposition", "/orderstatus", "/openposition", "/closeall",
        ]
    ):
        return "orders"

    if any(
        x in path_lower
        for x in [
            "/quotes", "/multiquotes", "/depth", "/history", "/intervals", "/symbol",
            "/search", "/expiry", "/optionsymbol", "/optiongreeks", "/multioptiongreeks",
            "/optionchain", "/ticker", "/syntheticfuture", "/instruments",
        ]
    ):
        return "data"

    return "utilities"


def load_bruno_endpoints():
    """Load all endpoints from Bruno .bru files"""
    endpoints = {"account": [], "orders": [], "data": [], "utilities": [], "websocket": []}

    collections_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "collections")
    bru_files = glob.glob(os.path.join(collections_path, "**", "*.bru"), recursive=True)

    parsed_endpoints = []

    for bru_file in bru_files:
        if os.path.basename(bru_file) == "collection.bru":
            continue

        endpoint = parse_bru_file(bru_file)
        if endpoint:
            parsed_endpoints.append(endpoint)

    parsed_endpoints.sort(key=lambda x: x.get("seq", 999))

    for endpoint in parsed_endpoints:
        if endpoint.get("type") == "websocket":
            category = "websocket"
        else:
            category = categorize_endpoint(endpoint.get("path", ""))

        clean_endpoint = {
            "name": endpoint.get("name", ""),
            "method": endpoint.get("method", "POST"),
            "path": endpoint.get("path", ""),
        }
        if "body" in endpoint:
            clean_endpoint["body"] = endpoint["body"]
        if "params" in endpoint:
            clean_endpoint["params"] = endpoint["params"]
        if "description" in endpoint:
            clean_endpoint["description"] = endpoint["description"]

        endpoints[category].append(clean_endpoint)

    for category in endpoints:
        endpoints[category].sort(key=lambda x: x.get("name", "").lower())

    return endpoints


@playground_router.get("/")
@limiter.limit(API_RATE_LIMIT)
async def index(request: Request, session: dict = Depends(check_session_validity)):
    """Render the API tester page"""
    login_username = session.get("user")
    api_key = get_api_key_for_tradingview(login_username) if login_username else None
    logger.info(f"Playground accessed by user: {login_username}")
    return templates.TemplateResponse(
        "playground.html",
        {"request": request, "login_username": login_username, "api_key": api_key or ""},
    )


@playground_router.get("/api-key")
@limiter.limit(API_RATE_LIMIT)
async def get_api_key(request: Request, session: dict = Depends(check_session_validity)):
    """Get the current user's API key"""
    login_username = session.get("user")
    if not login_username:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    api_key = get_api_key_for_tradingview(login_username)
    return JSONResponse({"api_key": api_key or ""})


@playground_router.get("/collections")
@limiter.limit(API_RATE_LIMIT)
async def get_collections(request: Request, session: dict = Depends(check_session_validity)):
    """Get all available API collections"""
    collections = []

    postman_path = os.path.join("collections", "postman", "realalgo.postman_collection.json")
    if os.path.exists(postman_path):
        with open(postman_path) as f:
            postman_data = json.load(f)
            collections.append({"name": "Postman Collection", "type": "postman", "data": postman_data})

    bruno_path = os.path.join("collections", "realalgo_bruno.json")
    if os.path.exists(bruno_path):
        with open(bruno_path) as f:
            bruno_data = json.load(f)
            collections.append({"name": "Bruno Collection", "type": "bruno", "data": bruno_data})

    return JSONResponse(collections)


@playground_router.get("/endpoints")
@limiter.limit(API_RATE_LIMIT)
async def get_endpoints(request: Request, session: dict = Depends(check_session_validity)):
    """Get structured list of all API endpoints from Bruno collections"""
    try:
        endpoints = load_bruno_endpoints()

        if not any(endpoints.values()):
            logger.warning("No endpoints loaded from Bruno collections")
            return JSONResponse(
                {"account": [], "orders": [], "data": [], "utilities": [], "websocket": []}
            )

        logger.info(f"Loaded {sum(len(v) for v in endpoints.values())} endpoints from Bruno collections")
        return JSONResponse(endpoints)

    except Exception as e:
        logger.error(f"Error loading endpoints: {e}")
        return JSONResponse({"error": "Failed to load endpoints"}, status_code=500)
