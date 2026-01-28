# routers/react_app.py
"""
FastAPI React Frontend Serving Router for RealAlgo
Serves the pre-built React app for migrated routes.
Requirements: 4.7
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.responses import FileResponse as StarletteFileResponse

# Path to the pre-built React frontend
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

react_router = APIRouter(tags=["react"])


def is_react_frontend_available() -> bool:
    """Check if the React frontend build exists."""
    index_html = FRONTEND_DIST / "index.html"
    return FRONTEND_DIST.exists() and index_html.exists()


def serve_react_app():
    """Serve the React app's index.html."""
    if not is_react_frontend_available():
        return HTMLResponse(
            content="""
        <html>
        <head><title>RealAlgo - Frontend Not Available</title></head>
        <body style="font-family: system-ui; padding: 40px; max-width: 600px; margin: 0 auto;">
            <h1>Frontend Not Built</h1>
            <p>The React frontend is not available. To build it:</p>
            <pre style="background: #f4f4f4; padding: 16px; border-radius: 8px;">
cd frontend
npm install
npm run build</pre>
            <p>Or use the pre-built version from the repository.</p>
        </body>
        </html>
        """,
            status_code=503,
        )

    index_path = FRONTEND_DIST / "index.html"
    return FileResponse(index_path, media_type="text/html")


# ============================================================
# Phase 2 Migrated Routes - These are served by React
# ============================================================


@react_router.get("/")
async def react_index():
    return serve_react_app()


@react_router.get("/login")
async def react_login():
    return serve_react_app()


@react_router.get("/setup")
async def react_setup():
    return serve_react_app()


@react_router.get("/reset-password")
async def react_reset_password():
    return serve_react_app()


@react_router.get("/download")
async def react_download():
    return serve_react_app()


@react_router.get("/error")
async def react_error():
    return serve_react_app()


@react_router.get("/rate-limited")
async def react_rate_limited():
    return serve_react_app()


@react_router.get("/broker")
async def react_broker():
    return serve_react_app()


@react_router.get("/broker/{broker}/totp")
async def react_broker_totp(broker: str):
    return serve_react_app()


@react_router.get("/dashboard")
async def react_dashboard():
    return serve_react_app()


# Trading pages
@react_router.get("/positions")
async def react_positions():
    return serve_react_app()


@react_router.get("/orderbook")
async def react_orderbook():
    return serve_react_app()


@react_router.get("/tradebook")
async def react_tradebook():
    return serve_react_app()


@react_router.get("/holdings")
async def react_holdings():
    return serve_react_app()


# Search pages
@react_router.get("/search/token")
async def react_search_token():
    return serve_react_app()


@react_router.get("/search")
async def react_search():
    return serve_react_app()


@react_router.get("/playground")
async def react_playground():
    return serve_react_app()


# ============================================================
# Phase 4 Routes - Charts, WebSocket & Sandbox
# ============================================================


@react_router.get("/platforms")
async def react_platforms():
    return serve_react_app()


@react_router.get("/tradingview")
async def react_tradingview():
    return serve_react_app()


@react_router.get("/gocharting")
async def react_gocharting():
    return serve_react_app()


@react_router.get("/pnl-tracker")
async def react_pnltracker():
    return serve_react_app()


@react_router.get("/websocket/test")
async def react_websocket_test():
    return serve_react_app()


@react_router.get("/sandbox")
async def react_sandbox():
    return serve_react_app()


@react_router.get("/sandbox/mypnl")
async def react_sandbox_mypnl():
    return serve_react_app()


@react_router.get("/analyzer")
async def react_analyzer():
    return serve_react_app()


# ============================================================
# Phase 6 Routes - Strategy & Automation
# ============================================================


@react_router.get("/strategy")
@react_router.get("/strategy/")
async def react_strategy_index():
    return serve_react_app()


@react_router.get("/strategy/new")
@react_router.get("/strategy/new/")
async def react_strategy_new():
    return serve_react_app()


@react_router.get("/strategy/{strategy_id}")
@react_router.get("/strategy/{strategy_id}/")
async def react_strategy_view(strategy_id: int):
    return serve_react_app()


@react_router.get("/strategy/{strategy_id}/configure")
@react_router.get("/strategy/{strategy_id}/configure/")
async def react_strategy_configure(strategy_id: int):
    return serve_react_app()


# Python Strategies
@react_router.get("/python")
@react_router.get("/python/")
async def react_python_index():
    return serve_react_app()


@react_router.get("/python/new")
@react_router.get("/python/new/")
async def react_python_new():
    return serve_react_app()


@react_router.get("/python/{strategy_id}/edit")
@react_router.get("/python/{strategy_id}/edit/")
async def react_python_edit(strategy_id: str):
    return serve_react_app()


@react_router.get("/python/{strategy_id}/logs")
@react_router.get("/python/{strategy_id}/logs/")
async def react_python_logs(strategy_id: str):
    return serve_react_app()


# Chartink Strategies
@react_router.get("/chartink")
@react_router.get("/chartink/")
async def react_chartink_index():
    return serve_react_app()


@react_router.get("/chartink/new")
@react_router.get("/chartink/new/")
async def react_chartink_new():
    return serve_react_app()


@react_router.get("/chartink/{strategy_id}")
@react_router.get("/chartink/{strategy_id}/")
async def react_chartink_view(strategy_id: int):
    return serve_react_app()


@react_router.get("/chartink/{strategy_id}/configure")
@react_router.get("/chartink/{strategy_id}/configure/")
async def react_chartink_configure(strategy_id: int):
    return serve_react_app()


# ============================================================
# Phase 7 Routes - Admin & Settings
# ============================================================


@react_router.get("/admin")
@react_router.get("/admin/")
async def react_admin_index():
    return serve_react_app()


@react_router.get("/admin/freeze")
@react_router.get("/admin/freeze/")
async def react_admin_freeze():
    return serve_react_app()


@react_router.get("/admin/holidays")
@react_router.get("/admin/holidays/")
async def react_admin_holidays():
    return serve_react_app()


@react_router.get("/admin/timings")
@react_router.get("/admin/timings/")
async def react_admin_timings():
    return serve_react_app()


# Telegram routes
@react_router.get("/telegram")
@react_router.get("/telegram/")
async def react_telegram_index():
    return serve_react_app()


@react_router.get("/telegram/config")
@react_router.get("/telegram/config/")
async def react_telegram_config():
    return serve_react_app()


@react_router.get("/telegram/users")
@react_router.get("/telegram/users/")
async def react_telegram_users():
    return serve_react_app()


@react_router.get("/telegram/analytics")
@react_router.get("/telegram/analytics/")
async def react_telegram_analytics():
    return serve_react_app()


# ============================================================
# Phase 7 Routes - Monitoring Dashboards
# ============================================================


@react_router.get("/security")
@react_router.get("/security/")
async def react_security():
    return serve_react_app()


@react_router.get("/traffic")
@react_router.get("/traffic/")
async def react_traffic():
    return serve_react_app()


@react_router.get("/latency")
@react_router.get("/latency/")
async def react_latency():
    return serve_react_app()


# ============================================================
# Phase 7 Routes - Settings & Action Center
# ============================================================


@react_router.get("/logs")
@react_router.get("/logs/")
async def react_logs():
    return serve_react_app()


@react_router.get("/logs/live")
@react_router.get("/logs/live/")
async def react_logs_live():
    return serve_react_app()


@react_router.get("/logs/sandbox")
@react_router.get("/logs/sandbox/")
async def react_logs_sandbox():
    return serve_react_app()


@react_router.get("/logs/security")
@react_router.get("/logs/security/")
async def react_logs_security():
    return serve_react_app()


@react_router.get("/logs/traffic")
@react_router.get("/logs/traffic/")
async def react_logs_traffic():
    return serve_react_app()


@react_router.get("/logs/latency")
@react_router.get("/logs/latency/")
async def react_logs_latency():
    return serve_react_app()


@react_router.get("/profile")
@react_router.get("/profile/")
async def react_profile():
    return serve_react_app()


@react_router.get("/action-center")
@react_router.get("/action-center/")
async def react_action_center():
    return serve_react_app()


@react_router.get("/historify")
@react_router.get("/historify/")
async def react_historify():
    return serve_react_app()


# ============================================================
# Flow Routes - Visual Workflow Automation
# ============================================================


@react_router.get("/flow")
@react_router.get("/flow/")
async def react_flow_index():
    return serve_react_app()


@react_router.get("/flow/editor/{workflow_id}")
@react_router.get("/flow/editor/{workflow_id}/")
async def react_flow_editor(workflow_id: int):
    return serve_react_app()


# ============================================================
# Static Assets - Always served for React app
# ============================================================


@react_router.get("/assets/{filename:path}")
async def serve_assets(filename: str):
    """Serve static assets with long cache headers."""
    assets_dir = FRONTEND_DIST / "assets"
    if not assets_dir.exists():
        return Response(content="Assets not found", status_code=404)

    file_path = assets_dir / filename
    if not file_path.exists():
        return Response(content="Asset not found", status_code=404)

    response = FileResponse(file_path)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@react_router.get("/favicon.ico")
async def serve_favicon():
    """Serve favicon."""
    favicon_path = FRONTEND_DIST / "favicon.ico"
    if not favicon_path.exists():
        return Response(content="Not found", status_code=404)
    return FileResponse(favicon_path)


@react_router.get("/logo.png")
async def serve_logo():
    """Serve logo."""
    logo_path = FRONTEND_DIST / "logo.png"
    if not logo_path.exists():
        return Response(content="Not found", status_code=404)
    return FileResponse(logo_path)


@react_router.get("/apple-touch-icon.png")
async def serve_apple_touch_icon():
    """Serve Apple touch icon."""
    icon_path = FRONTEND_DIST / "apple-touch-icon.png"
    if not icon_path.exists():
        return Response(content="Not found", status_code=404)
    return FileResponse(icon_path)


@react_router.get("/images/{filename:path}")
async def serve_images(filename: str):
    """Serve images from React dist."""
    images_dir = FRONTEND_DIST / "images"
    if not images_dir.exists():
        return Response(content="Images not found", status_code=404)

    file_path = images_dir / filename
    if not file_path.exists():
        return Response(content="Image not found", status_code=404)

    return FileResponse(file_path)


@react_router.get("/sounds/{filename:path}")
async def serve_sounds(filename: str):
    """Serve sounds from React dist."""
    sounds_dir = FRONTEND_DIST / "sounds"
    if not sounds_dir.exists():
        return Response(content="Sounds not found", status_code=404)

    file_path = sounds_dir / filename
    if not file_path.exists():
        return Response(content="Sound not found", status_code=404)

    return FileResponse(file_path)


@react_router.get("/docs/{filename:path}")
async def serve_docs(filename: str):
    """Serve docs from React dist."""
    docs_dir = FRONTEND_DIST / "docs"
    if not docs_dir.exists():
        return Response(content="Docs not found", status_code=404)

    file_path = docs_dir / filename
    if not file_path.exists():
        return Response(content="Doc not found", status_code=404)

    return FileResponse(file_path)
