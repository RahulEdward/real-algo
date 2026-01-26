# routers/flow.py
"""
FastAPI Flow Router for RealAlgo
Visual Workflow Automation - manages and executes workflows.
Requirements: 4.7
"""

import hmac
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from database.auth_db import get_api_key_for_tradingview
from dependencies_fastapi import check_session_validity, get_session

logger = logging.getLogger(__name__)

flow_router = APIRouter(prefix="/flow", tags=["flow"])


def get_current_api_key(session: dict):
    """Get API key for the current user from session"""
    username = session.get("user")
    if not username:
        return None
    return get_api_key_for_tradingview(username)


def get_webhook_base_url():
    """Get the base URL for webhooks based on server configuration"""
    host = os.getenv("HOST_SERVER", "http://127.0.0.1:5000")
    return host.rstrip("/")


# === Workflow CRUD Routes ===


@flow_router.get("/api/workflows")
async def list_workflows(request: Request, session: dict = Depends(check_session_validity)):
    """List all workflows"""
    from database.flow_db import get_all_workflows, get_workflow_executions

    workflows = get_all_workflows()
    items = []

    for wf in workflows:
        executions = get_workflow_executions(wf.id, limit=1)
        last_exec = executions[0] if executions else None

        items.append({
            "id": wf.id,
            "name": wf.name,
            "description": wf.description,
            "is_active": wf.is_active,
            "webhook_enabled": wf.webhook_enabled,
            "created_at": wf.created_at.isoformat() if wf.created_at else None,
            "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
            "last_execution_status": last_exec.status if last_exec else None,
        })

    return JSONResponse(items)


@flow_router.post("/api/workflows")
async def create_workflow(request: Request, session: dict = Depends(check_session_validity)):
    """Create a new workflow"""
    from database.flow_db import create_workflow

    data = await request.json()
    if not data:
        return JSONResponse({"error": "No data provided"}, status_code=400)

    name = data.get("name", "Untitled Workflow")
    description = data.get("description")
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    workflow = create_workflow(name=name, description=description, nodes=nodes, edges=edges)

    if not workflow:
        return JSONResponse({"error": "Failed to create workflow"}, status_code=500)

    return JSONResponse({
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "nodes": workflow.nodes,
        "edges": workflow.edges,
        "is_active": workflow.is_active,
        "webhook_token": workflow.webhook_token,
        "webhook_secret": workflow.webhook_secret,
        "webhook_enabled": workflow.webhook_enabled,
        "webhook_auth_type": workflow.webhook_auth_type,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    }, status_code=201)


@flow_router.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Get a workflow by ID"""
    from database.flow_db import get_workflow

    workflow = get_workflow(workflow_id)
    if not workflow:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    return JSONResponse({
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "nodes": workflow.nodes,
        "edges": workflow.edges,
        "is_active": workflow.is_active,
        "schedule_job_id": workflow.schedule_job_id,
        "webhook_token": workflow.webhook_token,
        "webhook_secret": workflow.webhook_secret,
        "webhook_enabled": workflow.webhook_enabled,
        "webhook_auth_type": workflow.webhook_auth_type,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    })


@flow_router.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Update a workflow"""
    from database.flow_db import update_workflow

    data = await request.json()
    if not data:
        return JSONResponse({"error": "No data provided"}, status_code=400)

    workflow = update_workflow(workflow_id, **data)
    if not workflow:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    return JSONResponse({
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "nodes": workflow.nodes,
        "edges": workflow.edges,
        "is_active": workflow.is_active,
        "webhook_token": workflow.webhook_token,
        "webhook_secret": workflow.webhook_secret,
        "webhook_enabled": workflow.webhook_enabled,
        "webhook_auth_type": workflow.webhook_auth_type,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    })


@flow_router.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Delete a workflow"""
    from database.flow_db import delete_workflow, get_workflow
    from services.flow_scheduler_service import get_flow_scheduler

    workflow = get_workflow(workflow_id)
    if not workflow:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    if workflow.is_active:
        scheduler = get_flow_scheduler()
        scheduler.remove_workflow_job(workflow_id)

    if delete_workflow(workflow_id):
        return JSONResponse({"status": "success", "message": "Workflow deleted"})
    else:
        return JSONResponse({"error": "Failed to delete workflow"}, status_code=500)


# === Activation/Deactivation Routes ===


@flow_router.post("/api/workflows/{workflow_id}/activate")
async def activate_workflow(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Activate a workflow"""
    from database.flow_db import activate_workflow as db_activate
    from database.flow_db import get_workflow, set_schedule_job_id
    from services.flow_price_monitor_service import get_flow_price_monitor
    from services.flow_scheduler_service import get_flow_scheduler

    workflow = get_workflow(workflow_id)
    if not workflow:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    if workflow.is_active:
        return JSONResponse({"status": "already_active", "message": "Workflow is already active"})

    api_key = get_current_api_key(session)
    if not api_key:
        return JSONResponse({"error": "API key not configured"}, status_code=400)

    nodes = workflow.nodes or []

    trigger_node = next(
        (n for n in nodes if n.get("type") in ["start", "webhookTrigger", "priceAlert"]), None
    )
    if not trigger_node:
        return JSONResponse({"error": "No trigger node found in workflow"}, status_code=400)

    trigger_type = trigger_node.get("type")
    trigger_data = trigger_node.get("data", {})

    try:
        if trigger_type == "start":
            schedule_type = trigger_data.get("scheduleType")
            if schedule_type and schedule_type != "manual":
                scheduler = get_flow_scheduler()
                scheduler.set_api_key(api_key)

                job_id = scheduler.add_workflow_job(
                    workflow_id=workflow_id,
                    schedule_type=schedule_type,
                    time_str=trigger_data.get("time", "09:15"),
                    days=trigger_data.get("days"),
                    execute_at=trigger_data.get("executeAt"),
                    interval_value=trigger_data.get("intervalValue"),
                    interval_unit=trigger_data.get("intervalUnit"),
                )
                set_schedule_job_id(workflow_id, job_id)

        elif trigger_type == "priceAlert":
            price_monitor = get_flow_price_monitor()
            price_monitor.add_alert(
                workflow_id=workflow_id,
                symbol=trigger_data.get("symbol", ""),
                exchange=trigger_data.get("exchange", "NSE"),
                condition=trigger_data.get("condition", "greater_than"),
                target_price=float(trigger_data.get("price", 0)),
                price_lower=trigger_data.get("priceLower"),
                price_upper=trigger_data.get("priceUpper"),
                percentage=trigger_data.get("percentage"),
                api_key=api_key,
            )

        db_activate(workflow_id, api_key=api_key)

        return JSONResponse({"status": "success", "message": f"Workflow activated with {trigger_type} trigger"})

    except Exception as e:
        logger.error(f"Failed to activate workflow {workflow_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@flow_router.post("/api/workflows/{workflow_id}/deactivate")
async def deactivate_workflow(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Deactivate a workflow"""
    from database.flow_db import deactivate_workflow as db_deactivate
    from database.flow_db import get_workflow, set_schedule_job_id
    from services.flow_price_monitor_service import get_flow_price_monitor
    from services.flow_scheduler_service import get_flow_scheduler

    workflow = get_workflow(workflow_id)
    if not workflow:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    if not workflow.is_active:
        return JSONResponse({"status": "already_inactive", "message": "Workflow is already inactive"})

    try:
        if workflow.schedule_job_id:
            scheduler = get_flow_scheduler()
            scheduler.remove_job(workflow.schedule_job_id)
            set_schedule_job_id(workflow_id, None)

        price_monitor = get_flow_price_monitor()
        price_monitor.remove_alert(workflow_id)

        db_deactivate(workflow_id)

        return JSONResponse({"status": "success", "message": "Workflow deactivated"})

    except Exception as e:
        logger.error(f"Failed to deactivate workflow {workflow_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# === Execution Routes ===


@flow_router.post("/api/workflows/{workflow_id}/execute")
async def execute_workflow_now(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Execute a workflow immediately"""
    from database.flow_db import get_workflow
    from services.flow_executor_service import execute_workflow

    workflow = get_workflow(workflow_id)
    if not workflow:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    api_key = get_current_api_key(session)
    if not api_key:
        return JSONResponse({"error": "API key not configured"}, status_code=400)

    try:
        result = execute_workflow(workflow_id, api_key=api_key)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Failed to execute workflow {workflow_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@flow_router.get("/api/workflows/{workflow_id}/executions")
async def get_workflow_executions(
    workflow_id: int,
    request: Request,
    limit: int = 20,
    session: dict = Depends(check_session_validity),
):
    """Get execution history for a workflow"""
    from database.flow_db import get_workflow_executions

    executions = get_workflow_executions(workflow_id, limit=limit)

    return JSONResponse([
        {
            "id": ex.id,
            "workflow_id": ex.workflow_id,
            "status": ex.status,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
            "logs": ex.logs,
            "error": ex.error,
        }
        for ex in executions
    ])


# === Webhook Routes ===


@flow_router.get("/api/workflows/{workflow_id}/webhook")
async def get_webhook_info(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Get webhook configuration for a workflow"""
    from database.flow_db import ensure_webhook_credentials, get_workflow

    workflow = get_workflow(workflow_id)
    if not workflow:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    ensure_webhook_credentials(workflow_id)
    workflow = get_workflow(workflow_id)

    base_url = get_webhook_base_url()
    webhook_url = f"{base_url}/flow/webhook/{workflow.webhook_token}"
    auth_type = workflow.webhook_auth_type or "payload"

    return JSONResponse({
        "webhook_token": workflow.webhook_token,
        "webhook_secret": workflow.webhook_secret,
        "webhook_enabled": workflow.webhook_enabled,
        "webhook_auth_type": auth_type,
        "webhook_url": webhook_url,
        "webhook_url_with_symbol": f"{webhook_url}/{{symbol}}",
        "webhook_url_with_secret": f"{webhook_url}?secret={workflow.webhook_secret}" if auth_type == "url" else None,
    })


@flow_router.post("/api/workflows/{workflow_id}/webhook/enable")
async def enable_webhook(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Enable webhook for a workflow"""
    from database.flow_db import enable_webhook, ensure_webhook_credentials, get_workflow

    ensure_webhook_credentials(workflow_id)

    result = enable_webhook(workflow_id)
    if not result:
        return JSONResponse({"error": "Failed to enable webhook"}, status_code=500)

    workflow = get_workflow(workflow_id)
    base_url = get_webhook_base_url()
    webhook_url = f"{base_url}/flow/webhook/{workflow.webhook_token}"
    auth_type = workflow.webhook_auth_type or "payload"

    return JSONResponse({
        "status": "success",
        "message": "Webhook enabled",
        "webhook_token": workflow.webhook_token,
        "webhook_secret": workflow.webhook_secret,
        "webhook_enabled": True,
        "webhook_auth_type": auth_type,
        "webhook_url": webhook_url,
        "webhook_url_with_symbol": f"{webhook_url}/{{symbol}}",
        "webhook_url_with_secret": f"{webhook_url}?secret={workflow.webhook_secret}" if auth_type == "url" else None,
    })


@flow_router.post("/api/workflows/{workflow_id}/webhook/disable")
async def disable_webhook(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Disable webhook for a workflow"""
    from database.flow_db import disable_webhook

    result = disable_webhook(workflow_id)
    if result:
        return JSONResponse({"status": "success", "message": "Webhook disabled"})
    return JSONResponse({"error": "Failed to disable webhook"}, status_code=500)


@flow_router.post("/api/workflows/{workflow_id}/webhook/regenerate")
async def regenerate_webhook(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Regenerate webhook token and secret"""
    from database.flow_db import get_workflow, regenerate_webhook_secret, regenerate_webhook_token

    new_token = regenerate_webhook_token(workflow_id)
    new_secret = regenerate_webhook_secret(workflow_id)

    if not new_token:
        return JSONResponse({"error": "Failed to regenerate token"}, status_code=500)

    workflow = get_workflow(workflow_id)
    base_url = get_webhook_base_url()
    webhook_url = f"{base_url}/flow/webhook/{workflow.webhook_token}"

    return JSONResponse({
        "status": "success",
        "message": "Webhook token and secret regenerated",
        "webhook_token": workflow.webhook_token,
        "webhook_secret": workflow.webhook_secret,
        "webhook_url": webhook_url,
        "webhook_url_with_symbol": f"{webhook_url}/{{symbol}}",
    })


@flow_router.post("/api/workflows/{workflow_id}/webhook/regenerate-secret")
async def regenerate_webhook_secret_route(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Regenerate webhook secret only"""
    from database.flow_db import regenerate_webhook_secret

    new_secret = regenerate_webhook_secret(workflow_id)
    if not new_secret:
        return JSONResponse({"error": "Failed to regenerate secret"}, status_code=500)

    return JSONResponse({
        "status": "success",
        "message": "Webhook secret regenerated",
        "webhook_secret": new_secret,
    })


@flow_router.post("/api/workflows/{workflow_id}/webhook/auth-type")
async def set_webhook_auth(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Set webhook auth type"""
    from database.flow_db import get_workflow, set_webhook_auth_type

    data = await request.json()
    auth_type = data.get("auth_type", "payload")

    result = set_webhook_auth_type(workflow_id, auth_type)
    if not result:
        return JSONResponse({"error": "Invalid auth type"}, status_code=400)

    workflow = get_workflow(workflow_id)
    base_url = get_webhook_base_url()
    webhook_url = f"{base_url}/flow/webhook/{workflow.webhook_token}"

    return JSONResponse({
        "status": "success",
        "message": f"Webhook auth type set to '{auth_type}'",
        "webhook_auth_type": auth_type,
        "webhook_url": webhook_url,
        "webhook_url_with_secret": f"{webhook_url}?secret={workflow.webhook_secret}" if auth_type == "url" else None,
    })


# === Webhook Trigger Routes (CSRF Exempt) ===


def _execute_webhook(token: str, webhook_data: dict = None, url_secret: str = None):
    """Internal function to execute webhook"""
    from database.flow_db import get_workflow_by_webhook_token
    from services.flow_executor_service import execute_workflow

    workflow = get_workflow_by_webhook_token(token)
    if not workflow:
        return JSONResponse({"error": "Invalid webhook token"}, status_code=404)

    if not workflow.webhook_enabled:
        return JSONResponse({"error": "Webhook is disabled"}, status_code=403)

    if not workflow.is_active:
        return JSONResponse({"error": "Workflow is not active"}, status_code=403)

    data = webhook_data or {}
    auth_type = workflow.webhook_auth_type or "payload"

    if workflow.webhook_secret:
        if auth_type == "url":
            if not url_secret:
                return JSONResponse(
                    {"error": "Missing webhook secret in URL. Use ?secret=your_secret"},
                    status_code=401,
                )
            if not hmac.compare_digest(url_secret, workflow.webhook_secret):
                return JSONResponse({"error": "Invalid webhook secret"}, status_code=401)
        else:
            provided_secret = data.pop("secret", "") or ""
            if not provided_secret:
                return JSONResponse(
                    {"error": "Missing webhook secret in payload. Add 'secret' field to JSON body"},
                    status_code=401,
                )
            if not hmac.compare_digest(provided_secret, workflow.webhook_secret):
                return JSONResponse({"error": "Invalid webhook secret"}, status_code=401)

    api_key = workflow.api_key
    if not api_key:
        api_key = os.getenv("REALALGO_API_KEY")

    if not api_key:
        logger.error(f"Webhook: No API key for workflow {workflow.id}")
        return JSONResponse(
            {"error": "No API key configured for workflow execution. Please re-activate the workflow."},
            status_code=500,
        )

    try:
        logger.info(f"Webhook triggered for workflow {workflow.id}: {workflow.name}")
        result = execute_workflow(workflow.id, webhook_data=data, api_key=api_key)
        return JSONResponse({
            "status": result.get("status", "success"),
            "message": f"Workflow '{workflow.name}' triggered",
            "execution_id": result.get("execution_id"),
            "workflow_id": workflow.id,
        })
    except Exception as e:
        logger.error(f"Webhook execution failed for workflow {workflow.id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@flow_router.post("/webhook/{token}")
async def trigger_webhook(token: str, request: Request):
    """
    Trigger a workflow via webhook (CSRF exempt)

    Authentication can be done via:
    1. URL query parameter: ?secret=your_secret (for Chartink, etc.)
    2. Payload field: {"secret": "your_secret", ...} (for TradingView, etc.)
    """
    url_secret = request.query_params.get("secret")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _execute_webhook(token, webhook_data=payload, url_secret=url_secret)


@flow_router.post("/webhook/{token}/{symbol}")
async def trigger_webhook_with_symbol(token: str, symbol: str, request: Request):
    """
    Trigger a workflow via webhook with symbol in URL path (CSRF exempt)

    The symbol is automatically injected into the webhook data.
    """
    url_secret = request.query_params.get("secret")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payload["symbol"] = symbol
    return _execute_webhook(token, webhook_data=payload, url_secret=url_secret)


# === Monitor Status Route ===


@flow_router.get("/api/monitor/status")
async def get_monitor_status(request: Request, session: dict = Depends(check_session_validity)):
    """Get price monitor status"""
    from services.flow_price_monitor_service import get_flow_price_monitor

    monitor = get_flow_price_monitor()
    return JSONResponse(monitor.get_status())


# === Export/Import Routes ===


@flow_router.get("/api/workflows/{workflow_id}/export")
async def export_workflow(workflow_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Export a workflow"""
    from database.flow_db import get_workflow

    workflow = get_workflow(workflow_id)
    if not workflow:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    return JSONResponse({
        "name": workflow.name,
        "description": workflow.description,
        "nodes": workflow.nodes,
        "edges": workflow.edges,
        "version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
    })


@flow_router.post("/api/workflows/import")
async def import_workflow(request: Request, session: dict = Depends(check_session_validity)):
    """Import a workflow"""
    from database.flow_db import create_workflow

    data = await request.json()
    if not data:
        return JSONResponse({"error": "No data provided"}, status_code=400)

    name = data.get("name", "Imported Workflow")
    description = data.get("description")
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    workflow = create_workflow(
        name=f"{name} (imported)", description=description, nodes=nodes, edges=edges
    )

    if workflow:
        return JSONResponse({"status": "success", "workflow_id": workflow.id}, status_code=201)
    return JSONResponse({"error": "Failed to import workflow"}, status_code=500)
