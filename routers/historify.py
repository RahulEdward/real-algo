# routers/historify.py
"""
FastAPI Historify Router for RealAlgo
Handles historical market data management.
Requirements: 4.7
"""

import io
import os
import tempfile
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from database.auth_db import get_api_key_for_tradingview
from dependencies_fastapi import check_session_validity, get_session
from utils.logging import get_logger

logger = get_logger(__name__)

historify_router = APIRouter(prefix="/historify", tags=["historify"])

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB


# =============================================================================
# Watchlist API Endpoints
# =============================================================================


@historify_router.get("/api/watchlist")
async def get_watchlist(request: Request, session: dict = Depends(check_session_validity)):
    """Get all symbols in the watchlist."""
    try:
        from services.historify_service import get_watchlist as service_get_watchlist

        success, response, status_code = service_get_watchlist()
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error getting watchlist: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.post("/api/watchlist")
async def add_watchlist(request: Request, session: dict = Depends(check_session_validity)):
    """Add a symbol to the watchlist."""
    try:
        from services.historify_service import add_to_watchlist

        data = await request.json()
        symbol = data.get("symbol", "").upper()
        exchange = data.get("exchange", "").upper()
        display_name = data.get("display_name")

        success, response, status_code = add_to_watchlist(symbol, exchange, display_name)
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error adding to watchlist: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.delete("/api/watchlist")
async def remove_watchlist(request: Request, session: dict = Depends(check_session_validity)):
    """Remove a symbol from the watchlist."""
    try:
        from services.historify_service import remove_from_watchlist

        data = await request.json()
        symbol = data.get("symbol", "").upper()
        exchange = data.get("exchange", "").upper()

        success, response, status_code = remove_from_watchlist(symbol, exchange)
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error removing from watchlist: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.post("/api/watchlist/bulk")
async def bulk_add_watchlist(request: Request, session: dict = Depends(check_session_validity)):
    """Add multiple symbols to the watchlist."""
    try:
        from services.historify_service import bulk_add_to_watchlist

        data = await request.json()
        symbols = data.get("symbols", [])

        success, response, status_code = bulk_add_to_watchlist(symbols)
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error bulk adding to watchlist: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# Data Download Endpoints
# =============================================================================


@historify_router.post("/api/download")
async def download_data(request: Request, session: dict = Depends(check_session_validity)):
    """Download historical data for a symbol."""
    try:
        from services.historify_service import download_data as service_download_data

        data = await request.json()
        symbol = data.get("symbol", "").upper()
        exchange = data.get("exchange", "").upper()
        interval = data.get("interval", "D")
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        user = session.get("user")
        api_key = get_api_key_for_tradingview(user)

        if not api_key:
            return JSONResponse(
                {"status": "error", "message": "No API key found. Please generate an API key first."},
                status_code=400,
            )

        success, response, status_code = service_download_data(
            symbol=symbol, exchange=exchange, interval=interval,
            start_date=start_date, end_date=end_date, api_key=api_key,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error downloading data: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.post("/api/download/watchlist")
async def download_watchlist(request: Request, session: dict = Depends(check_session_validity)):
    """Download data for all symbols in the watchlist."""
    try:
        from services.historify_service import download_watchlist_data

        data = await request.json()
        interval = data.get("interval", "D")
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        user = session.get("user")
        api_key = get_api_key_for_tradingview(user)

        if not api_key:
            return JSONResponse(
                {"status": "error", "message": "No API key found. Please generate an API key first."},
                status_code=400,
            )

        success, response, status_code = download_watchlist_data(
            interval=interval, start_date=start_date, end_date=end_date, api_key=api_key
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error downloading watchlist data: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# Data Retrieval Endpoints
# =============================================================================


@historify_router.get("/api/data")
async def get_chart_data(
    request: Request,
    symbol: str = Query(default=""),
    exchange: str = Query(default=""),
    interval: str = Query(default="D"),
    start_date: str = Query(default=None),
    end_date: str = Query(default=None),
    session: dict = Depends(check_session_validity),
):
    """Get OHLCV data for charting."""
    try:
        from services.historify_service import get_chart_data as service_get_chart_data

        success, response, status_code = service_get_chart_data(
            symbol=symbol.upper(), exchange=exchange.upper(),
            interval=interval, start_date=start_date, end_date=end_date,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error getting chart data: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.get("/api/catalog")
async def get_catalog(request: Request, session: dict = Depends(check_session_validity)):
    """Get catalog of all available data."""
    try:
        from services.historify_service import get_data_catalog

        success, response, status_code = get_data_catalog()
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error getting catalog: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.get("/api/symbol-info")
async def get_symbol_info(
    request: Request,
    symbol: str = Query(default=""),
    exchange: str = Query(default=""),
    interval: str = Query(default=None),
    session: dict = Depends(check_session_validity),
):
    """Get data availability info for a symbol."""
    try:
        from services.historify_service import get_symbol_data_info

        success, response, status_code = get_symbol_data_info(symbol.upper(), exchange.upper(), interval)
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error getting symbol info: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# Export Endpoints
# =============================================================================


@historify_router.post("/api/export")
async def export_data(request: Request, session: dict = Depends(check_session_validity)):
    """Export data to CSV and return download link."""
    try:
        from services.historify_service import export_data_to_csv

        data = await request.json()
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        interval = data.get("interval")
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        output_dir = tempfile.gettempdir()

        success, response, status_code = export_data_to_csv(
            output_dir=output_dir, symbol=symbol, exchange=exchange,
            interval=interval, start_date=start_date, end_date=end_date,
        )

        if success:
            request.session["export_file"] = response.get("file_path")

        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.get("/api/export/download")
async def download_export(request: Request, session: dict = Depends(check_session_validity)):
    """Download the exported CSV file."""
    file_path = None
    try:
        file_path = request.session.get("export_file")

        if not file_path or not os.path.exists(file_path):
            return JSONResponse({"status": "error", "message": "Export file not found"}, status_code=404)

        temp_dir = tempfile.gettempdir()
        abs_path = os.path.abspath(file_path)
        if not abs_path.startswith(os.path.abspath(temp_dir)):
            return JSONResponse({"status": "error", "message": "Invalid file path"}, status_code=400)

        filename = os.path.basename(file_path)
        request.session.pop("export_file", None)

        def generate_and_cleanup():
            try:
                with open(file_path) as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk
            finally:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass

        return StreamingResponse(
            generate_and_cleanup(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.error(f"Error downloading export: {e}")
        traceback.print_exc()
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# Bulk Export Endpoints
# =============================================================================


@historify_router.post("/api/export/preview")
async def get_export_preview(request: Request, session: dict = Depends(check_session_validity)):
    """Get preview of what will be exported."""
    try:
        from database.historify_db import get_export_preview as db_get_preview

        data = await request.json()
        symbols = data.get("symbols")
        interval = data.get("interval")
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        start_timestamp = None
        end_timestamp = None
        if start_date:
            start_timestamp = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        if end_date:
            end_timestamp = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp()) + 86400

        preview = db_get_preview(
            symbols=symbols, interval=interval,
            start_timestamp=start_timestamp, end_timestamp=end_timestamp,
        )

        return JSONResponse({"status": "success", "data": preview})
    except Exception as e:
        logger.error(f"Error getting export preview: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.post("/api/export/bulk")
async def bulk_export(request: Request, session: dict = Depends(check_session_validity)):
    """Export data in various formats (CSV, TXT, ZIP, Parquet)."""
    try:
        from database.historify_db import (
            export_bulk_csv, export_to_parquet, export_to_txt, export_to_zip,
            is_custom_interval, parse_interval,
        )

        data = await request.json()
        format_type = data.get("format", "csv").lower()
        symbols = data.get("symbols")
        interval = data.get("interval")
        intervals = data.get("intervals")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        split_by = data.get("split_by", "symbol")
        compression = data.get("compression", "zstd")

        if intervals is not None:
            if not isinstance(intervals, list):
                return JSONResponse({"status": "error", "message": "intervals must be an array"}, status_code=400)
            if len(intervals) == 0:
                return JSONResponse({"status": "error", "message": "At least one interval must be specified"}, status_code=400)
            intervals = list(set(intervals))
            invalid = [i for i in intervals if parse_interval(i) is None]
            if invalid:
                return JSONResponse({"status": "error", "message": f"Invalid intervals: {invalid}"}, status_code=400)

        start_timestamp = None
        end_timestamp = None
        if start_date:
            start_timestamp = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        if end_date:
            end_timestamp = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp()) + 86400

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        if symbols and len(symbols) == 1:
            base_name = f"historify_{symbols[0]['symbol']}_{timestamp_str}"
        else:
            base_name = f"historify_export_{timestamp_str}"

        has_computed = intervals and any(is_custom_interval(i) for i in intervals)
        if (intervals and len(intervals) > 1) or has_computed:
            format_type = "zip"

        if format_type == "parquet":
            file_ext = ".parquet"
        elif format_type == "zip":
            file_ext = ".zip"
        elif format_type == "txt":
            file_ext = ".txt"
        else:
            file_ext = ".csv"

        output_path = os.path.join(tempfile.gettempdir(), f"{base_name}{file_ext}")

        if format_type == "parquet":
            success, message, record_count = export_to_parquet(
                output_path=output_path, symbols=symbols,
                interval=intervals[0] if intervals else interval,
                start_timestamp=start_timestamp, end_timestamp=end_timestamp,
                compression=compression,
            )
            mime_type = "application/octet-stream"
        elif format_type == "zip":
            success, message, record_count = export_to_zip(
                output_path=output_path, symbols=symbols,
                intervals=intervals if intervals else ([interval] if interval else None),
                start_timestamp=start_timestamp, end_timestamp=end_timestamp,
                split_by=split_by,
            )
            mime_type = "application/zip"
        elif format_type == "txt":
            success, message, record_count = export_to_txt(
                output_path=output_path, symbols=symbols,
                interval=intervals[0] if intervals else interval,
                start_timestamp=start_timestamp, end_timestamp=end_timestamp,
            )
            mime_type = "text/plain"
        else:
            success, message, record_count = export_bulk_csv(
                output_path=output_path, symbols=symbols if symbols else [],
                interval=intervals[0] if intervals else interval,
                start_timestamp=start_timestamp, end_timestamp=end_timestamp,
            )
            mime_type = "text/csv"

        if not success:
            return JSONResponse({"status": "error", "message": message}, status_code=400)

        request.session["bulk_export_file"] = output_path
        request.session["bulk_export_mime"] = mime_type
        request.session["bulk_export_name"] = f"{base_name}{file_ext}"

        return JSONResponse({
            "status": "success", "message": message,
            "record_count": record_count, "filename": f"{base_name}{file_ext}",
        })

    except Exception as e:
        logger.error(f"Error in bulk export: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.get("/api/export/bulk/download")
async def download_bulk_export(request: Request, session: dict = Depends(check_session_validity)):
    """Download the bulk exported file."""
    file_path = None
    try:
        file_path = request.session.get("bulk_export_file")
        mime_type = request.session.get("bulk_export_mime", "application/octet-stream")
        filename = request.session.get("bulk_export_name", "export.bin")

        if not file_path or not os.path.exists(file_path):
            return JSONResponse({"status": "error", "message": "Export file not found"}, status_code=404)

        temp_dir = tempfile.gettempdir()
        abs_path = os.path.abspath(file_path)
        if not abs_path.startswith(os.path.abspath(temp_dir)):
            return JSONResponse({"status": "error", "message": "Invalid file path"}, status_code=400)

        request.session.pop("bulk_export_file", None)
        request.session.pop("bulk_export_mime", None)
        request.session.pop("bulk_export_name", None)

        def generate_and_cleanup():
            try:
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        yield chunk
            finally:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass

        return StreamingResponse(
            generate_and_cleanup(),
            media_type=mime_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.error(f"Error downloading bulk export: {e}")
        traceback.print_exc()
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# Utility Endpoints
# =============================================================================


@historify_router.get("/api/intervals")
async def get_intervals(request: Request, session: dict = Depends(check_session_validity)):
    """Get supported intervals from the broker."""
    try:
        from services.historify_service import get_supported_timeframes

        user = session.get("user")
        api_key = get_api_key_for_tradingview(user)

        if not api_key:
            return JSONResponse(
                {"status": "error", "message": "No API key found. Please generate an API key first."},
                status_code=400,
            )

        success, response, status_code = get_supported_timeframes(api_key)
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error getting intervals: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.get("/api/historify-intervals")
async def get_historify_intervals(request: Request, session: dict = Depends(check_session_validity)):
    """Get Historify-specific interval configuration."""
    try:
        from services.historify_service import get_historify_intervals as service_get_intervals

        success, response, status_code = service_get_intervals()
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error getting historify intervals: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.get("/api/exchanges")
async def get_exchanges(request: Request, session: dict = Depends(check_session_validity)):
    """Get list of supported exchanges."""
    try:
        from services.historify_service import get_exchanges as service_get_exchanges

        success, response, status_code = service_get_exchanges()
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error getting exchanges: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.get("/api/stats")
async def get_stats(request: Request, session: dict = Depends(check_session_validity)):
    """Get database statistics."""
    try:
        from services.historify_service import get_stats as service_get_stats

        success, response, status_code = service_get_stats()
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.delete("/api/delete")
async def delete_data(request: Request, session: dict = Depends(check_session_validity)):
    """Delete data for a symbol."""
    try:
        from services.historify_service import delete_symbol_data

        data = await request.json()
        symbol = data.get("symbol", "").upper()
        exchange = data.get("exchange", "").upper()
        interval = data.get("interval")

        success, response, status_code = delete_symbol_data(symbol, exchange, interval)
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.error(f"Error deleting data: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# CSV Upload Endpoint
# =============================================================================


@historify_router.post("/api/upload")
async def upload_data(
    request: Request,
    file: UploadFile = File(...),
    symbol: str = Form(...),
    exchange: str = Form(...),
    interval: str = Form(...),
    session: dict = Depends(check_session_validity),
):
    """Upload CSV or Parquet file with OHLCV data."""
    temp_path = None
    try:
        from services.historify_service import upload_csv_data, upload_parquet_data

        if file.filename == "":
            return JSONResponse({"status": "error", "message": "No file selected"}, status_code=400)

        filename_lower = file.filename.lower()
        is_csv = filename_lower.endswith(".csv")
        is_parquet = filename_lower.endswith(".parquet")

        if not is_csv and not is_parquet:
            return JSONResponse({"status": "error", "message": "File must be CSV or Parquet"}, status_code=400)

        content = await file.read()
        file_size = len(content)

        if file_size > MAX_UPLOAD_SIZE:
            return JSONResponse(
                {"status": "error", "message": f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB"},
                status_code=400,
            )

        symbol = symbol.upper()
        exchange = exchange.upper()

        if not symbol or not exchange or not interval:
            return JSONResponse(
                {"status": "error", "message": "Symbol, exchange, and interval are required"},
                status_code=400,
            )

        suffix = ".csv" if is_csv else ".parquet"
        with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, prefix="historify_upload_", delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(content)

        try:
            if is_csv:
                success, response, status_code = upload_csv_data(
                    file_path=temp_path, symbol=symbol, exchange=exchange, interval=interval
                )
            else:
                success, response, status_code = upload_parquet_data(
                    file_path=temp_path, symbol=symbol, exchange=exchange, interval=interval
                )
            return JSONResponse(response, status_code=status_code)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logger.error(f"Error uploading data: {e}")
        traceback.print_exc()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@historify_router.get("/api/sample/{format_type}")
async def download_sample(format_type: str, request: Request, session: dict = Depends(check_session_validity)):
    """Download sample CSV or Parquet file for import reference."""
    import pandas as pd

    try:
        sample_data = {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "time": ["09:15:00", "09:15:00", "09:15:00", "09:15:00", "09:15:00"],
            "open": [100.0, 102.5, 101.0, 103.0, 104.5],
            "high": [103.0, 104.0, 103.5, 105.0, 106.0],
            "low": [99.5, 101.0, 100.5, 102.5, 103.5],
            "close": [102.5, 101.0, 103.0, 104.5, 105.5],
            "volume": [10000, 12000, 11000, 15000, 13000],
            "oi": [0, 0, 0, 0, 0],
        }
        df = pd.DataFrame(sample_data)

        if format_type == "csv":
            output = io.StringIO()
            df.to_csv(output, index=False)
            output.seek(0)
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=sample_ohlcv.csv"},
            )
        elif format_type == "parquet":
            output = io.BytesIO()
            df.to_parquet(output, index=False, engine="pyarrow", compression="zstd")
            output.seek(0)
            return Response(
                content=output.getvalue(),
                media_type="application/octet-stream",
                headers={"Content-Disposition": "attachment; filename=sample_ohlcv.parquet"},
            )
        else:
            return JSONResponse(
                {"status": "error", "message": "Invalid format. Use csv or parquet"},
                status_code=400,
            )

    except Exception as e:
        logger.error(f"Error generating sample: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
