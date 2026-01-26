# routers/python_strategy.py
"""
FastAPI Python Strategy Router for RealAlgo
Handles Python strategy hosting with process isolation, scheduling, SSE.
Requirements: 4.7
"""

import atexit
import json
import logging
import os
import platform
import queue
import signal
import subprocess
import sys
import threading
from datetime import datetime, time
from pathlib import Path

import psutil
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from werkzeug.utils import secure_filename

from database.market_calendar_db import get_market_hours_status, is_market_holiday, is_market_open
from dependencies_fastapi import check_session_validity, get_session
from utils.logging import get_logger

logger = get_logger(__name__)

python_strategy_router = APIRouter(prefix="/python", tags=["python_strategy"])
templates = Jinja2Templates(directory="templates")

# Timezone configuration - Indian Standard Time
IST = pytz.timezone("Asia/Kolkata")

# Global storage with thread locks for safety
RUNNING_STRATEGIES = {}
STRATEGY_CONFIGS = {}
SCHEDULER = None
PROCESS_LOCK = threading.Lock()

# SSE (Server-Sent Events) for real-time status updates
SSE_SUBSCRIBERS = []
SSE_LOCK = threading.Lock()

# File paths
STRATEGIES_DIR = Path("strategies") / "scripts"
LOGS_DIR = Path("log") / "strategies"
CONFIG_FILE = Path("strategies") / "strategy_configs.json"

# Detect operating system
OS_TYPE = platform.system().lower()
IS_WINDOWS = OS_TYPE == "windows"
IS_MAC = OS_TYPE == "darwin"
IS_LINUX = OS_TYPE == "linux"

# Resource limits
STRATEGY_MEMORY_LIMIT_MB = 512
STRATEGY_CPU_TIME_LIMIT_SEC = 3600


def broadcast_status_update(strategy_id: str, status: str, message: str = None):
    """Broadcast strategy status update to all SSE subscribers"""
    event_data = {
        "strategy_id": strategy_id,
        "status": status,
        "message": message,
        "timestamp": datetime.now(IST).isoformat(),
    }
    event = f"data: {json.dumps(event_data)}\n\n"

    with SSE_LOCK:
        active_subscribers = []
        for q in SSE_SUBSCRIBERS:
            try:
                q.put_nowait(event)
                active_subscribers.append(q)
            except:
                pass
        SSE_SUBSCRIBERS.clear()
        SSE_SUBSCRIBERS.extend(active_subscribers)


def init_scheduler():
    """Initialize the APScheduler with IST timezone"""
    global SCHEDULER
    if SCHEDULER is None:
        SCHEDULER = BackgroundScheduler(daemon=True, timezone=IST)
        SCHEDULER.start()
        logger.debug(f"Scheduler initialized with IST timezone on {OS_TYPE}")

        SCHEDULER.add_job(
            func=daily_trading_day_check,
            trigger=CronTrigger(hour=0, minute=1, timezone=IST),
            id="daily_trading_day_check",
            replace_existing=True,
        )
        logger.debug("Daily trading day check scheduled at 00:01 IST")

        SCHEDULER.add_job(
            func=market_hours_enforcer,
            trigger="interval",
            minutes=1,
            id="market_hours_enforcer",
            replace_existing=True,
        )
        logger.debug("Market hours enforcer scheduled (runs every minute)")


def load_configs():
    """Load strategy configurations from file"""
    global STRATEGY_CONFIGS
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                STRATEGY_CONFIGS = json.load(f)
            logger.debug(f"Loaded {len(STRATEGY_CONFIGS)} strategy configurations")
        except Exception as e:
            logger.error(f"Failed to load configs: {e}")
            STRATEGY_CONFIGS = {}


def save_configs():
    """Save strategy configurations to file"""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(STRATEGY_CONFIGS, f, indent=2, default=str, ensure_ascii=False)
        logger.info("Configurations saved")
    except Exception as e:
        logger.error(f"Failed to save configs: {e}")


def verify_strategy_ownership(strategy_id, user_id, return_config=False):
    """Verify that a user owns a strategy."""
    if not strategy_id or ".." in strategy_id or "/" in strategy_id or "\\" in strategy_id:
        return False, JSONResponse({"status": "error", "message": "Invalid strategy ID"}, status_code=400)

    if strategy_id not in STRATEGY_CONFIGS:
        return False, JSONResponse({"status": "error", "message": "Strategy not found"}, status_code=404)

    config = STRATEGY_CONFIGS[strategy_id]
    strategy_owner = config.get("user_id")
    if strategy_owner and strategy_owner != user_id:
        return False, JSONResponse({"status": "error", "message": "Unauthorized access to strategy"}, status_code=403)

    if return_config:
        return True, config
    return True, None


def ensure_directories():
    """Ensure all required directories exist"""
    global STRATEGIES_DIR, LOGS_DIR
    try:
        STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Directories initialized on {OS_TYPE}")
    except PermissionError as e:
        if STRATEGIES_DIR.exists() and LOGS_DIR.exists():
            logger.warning(f"Directories exist but no write permission: {e}")
        else:
            import tempfile
            temp_base = Path(tempfile.gettempdir()) / "realalgo"
            STRATEGIES_DIR = temp_base / "strategies" / "scripts"
            LOGS_DIR = temp_base / "log" / "strategies"
            STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            logger.warning(f"Using temporary directories due to permission issues: {temp_base}")
    except Exception as e:
        logger.error(f"Failed to create directories: {e}")


def get_ist_time():
    """Get current IST time"""
    return datetime.now(IST)


def format_ist_time(dt):
    """Format datetime to IST string"""
    if dt:
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except:
                return dt
        if not dt.tzinfo:
            dt = IST.localize(dt)
        else:
            dt = dt.astimezone(IST)
        return dt.strftime("%Y-%m-%d %H:%M:%S IST")
    return ""


def get_python_executable():
    """Get the correct Python executable for the current OS"""
    return sys.executable


def set_resource_limits():
    """Set resource limits for strategy subprocess (Unix/Mac only)."""
    if IS_WINDOWS:
        return

    try:
        import resource
        memory_bytes = STRATEGY_MEMORY_LIMIT_MB * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            resource.setrlimit(resource.RLIMIT_DATA, (memory_bytes, memory_bytes))
        except (OSError, ValueError) as e:
            logger.debug(f"Could not set memory limit: {e}")

        try:
            resource.setrlimit(resource.RLIMIT_CPU, (STRATEGY_CPU_TIME_LIMIT_SEC, STRATEGY_CPU_TIME_LIMIT_SEC))
        except (OSError, ValueError) as e:
            logger.debug(f"Could not set CPU limit: {e}")

        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        except (OSError, ValueError) as e:
            logger.debug(f"Could not set file descriptor limit: {e}")

        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except (OSError, ValueError) as e:
            logger.debug(f"Could not set process limit: {e}")

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Could not set resource limits: {e}")


def create_subprocess_args():
    """Create platform-specific subprocess arguments"""
    args = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "universal_newlines": False,
        "bufsize": 1,
    }

    if IS_WINDOWS:
        args["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        args["startupinfo"] = subprocess.STARTUPINFO()
        args["startupinfo"].dwFlags |= subprocess.STARTF_USESHOWWINDOW
    else:
        try:
            args["start_new_session"] = True
        except Exception as e:
            logger.warning(f"Could not set start_new_session: {e}")
        args["preexec_fn"] = set_resource_limits

    return args


def check_master_contract_ready(skip_on_startup=False):
    """Check if master contracts are ready for the current broker"""
    try:
        broker = None
        if not broker:
            from sqlalchemy import desc
            from database.auth_db import Auth
            auth_obj = Auth.query.filter_by(is_revoked=False).order_by(desc(Auth.id)).first()
            if auth_obj:
                broker = auth_obj.broker

        if not broker:
            if skip_on_startup:
                logger.info("No broker found during startup - skipping master contract check")
                return True, "Skipping check during startup"
            logger.warning("No broker found for master contract check")
            return False, "No broker session found"

        from database.master_contract_status_db import check_if_ready
        is_ready = check_if_ready(broker)
        if is_ready:
            return True, "Master contracts ready"
        else:
            return False, f"Master contracts not ready for broker: {broker}"

    except Exception as e:
        logger.error(f"Error checking master contract readiness: {e}")
        return False, f"Error checking master contract readiness: {str(e)}"


def start_strategy_process(strategy_id):
    """Start a strategy in a new process - cross-platform implementation"""
    with PROCESS_LOCK:
        if strategy_id in RUNNING_STRATEGIES:
            return False, "Strategy already running"

        config = STRATEGY_CONFIGS.get(strategy_id)
        if not config:
            return False, "Strategy configuration not found"

        file_path = Path(config["file_path"])
        if not file_path.exists():
            return False, f"Strategy file not found: {file_path}"

        if not IS_WINDOWS:
            if not os.access(file_path, os.R_OK):
                logger.error(f"Strategy file {file_path} is not readable.")
                return False, f"Strategy file is not readable. Run: chmod +r {file_path}"

            if not os.access(file_path, os.X_OK):
                logger.warning(f"Strategy file {file_path} is not executable. Setting execute permission.")
                try:
                    os.chmod(file_path, 0o755)
                except Exception as e:
                    logger.warning(f"Could not set execute permission: {e}")

        contracts_ready, contract_message = check_master_contract_ready()
        if not contracts_ready:
            logger.warning(f"Cannot start strategy {strategy_id}: {contract_message}")
            return False, f"Master contract dependency not met: {contract_message}"

        try:
            ist_now = get_ist_time()
            log_file = LOGS_DIR / f"{strategy_id}_{ist_now.strftime('%Y%m%d_%H%M%S')}_IST.log"

            log_file.parent.mkdir(parents=True, exist_ok=True)
            if not IS_WINDOWS:
                try:
                    os.chmod(log_file.parent, 0o755)
                except:
                    pass

            if not os.access(log_file.parent, os.W_OK):
                logger.error(f"Cannot write to log directory {log_file.parent}")
                return False, f"Log directory is not writable. Check permissions for {log_file.parent}"

            try:
                log_handle = open(log_file, "w", encoding="utf-8", buffering=1)
            except PermissionError as e:
                logger.error(f"Permission denied creating log file: {e}")
                return False, "Permission denied creating log file. Check directory permissions."
            except Exception as e:
                logger.error(f"Error creating log file: {e}")
                return False, f"Error creating log file: {str(e)}"

            log_handle.write(f"=== Strategy Started at {ist_now.strftime('%Y-%m-%d %H:%M:%S IST')} ===\n")
            log_handle.write(f"=== Platform: {OS_TYPE} ===\n\n")
            log_handle.flush()

            subprocess_args = create_subprocess_args()
            subprocess_args["stdout"] = log_handle
            subprocess_args["stderr"] = subprocess.STDOUT
            subprocess_args["cwd"] = str(Path.cwd())

            cmd = [get_python_executable(), "-u", str(file_path.absolute())]

            logger.info(f"Executing command: {' '.join(cmd)}")
            logger.debug(f"Working directory: {subprocess_args.get('cwd', 'current')}")

            try:
                process = subprocess.Popen(cmd, **subprocess_args)
            except PermissionError as e:
                log_handle.close()
                logger.error(f"Permission denied executing strategy: {e}")
                return False, "Permission denied. Check file permissions and Python executable access."
            except OSError as e:
                log_handle.close()
                if "preexec_fn" in str(e):
                    logger.error(f"Process isolation error: {e}")
                    return False, "Process isolation failed. Please restart the application."
                else:
                    logger.error(f"OS error starting process: {e}")
                    return False, f"OS error: {str(e)}"
            except Exception as e:
                log_handle.close()
                logger.error(f"Unexpected error starting process: {e}")
                return False, f"Failed to start process: {str(e)}"

            RUNNING_STRATEGIES[strategy_id] = {
                "process": process,
                "pid": process.pid,
                "started_at": ist_now,
                "log_file": str(log_file),
                "log_handle": log_handle,
            }

            STRATEGY_CONFIGS[strategy_id]["is_running"] = True
            STRATEGY_CONFIGS[strategy_id]["last_started"] = ist_now.isoformat()
            STRATEGY_CONFIGS[strategy_id]["pid"] = process.pid
            STRATEGY_CONFIGS[strategy_id].pop("is_error", None)
            STRATEGY_CONFIGS[strategy_id].pop("error_message", None)
            STRATEGY_CONFIGS[strategy_id].pop("error_time", None)
            save_configs()

            broadcast_status_update(strategy_id, "running", f"Started at {ist_now.strftime('%H:%M:%S IST')}")

            logger.info(f"Started strategy {strategy_id} with PID {process.pid} at {ist_now.strftime('%H:%M:%S IST')} on {OS_TYPE}")
            return True, f"Strategy started with PID {process.pid} at {ist_now.strftime('%H:%M:%S IST')}"

        except Exception as e:
            logger.error(f"Failed to start strategy {strategy_id}: {e}")
            return False, f"Failed to start strategy: {str(e)}"


def terminate_process_cross_platform(pid):
    """Terminate a process in a cross-platform way"""
    try:
        process = psutil.Process(pid)
        children = process.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass

        process.terminate()
        gone, alive = psutil.wait_procs([process] + children, timeout=3)
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass

    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        logger.error(f"Error terminating process {pid}: {e}")


def check_process_status(pid):
    """Check if a process is still running - cross-platform"""
    try:
        if psutil.pid_exists(pid):
            process = psutil.Process(pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False


def close_log_handle_safely(strategy_info):
    """Safely close a log file handle"""
    if not strategy_info:
        return
    log_handle = strategy_info.get("log_handle")
    if log_handle:
        try:
            if not log_handle.closed:
                log_handle.flush()
                log_handle.close()
        except Exception as e:
            logger.debug(f"Error closing log handle: {e}")
        finally:
            strategy_info["log_handle"] = None


def stop_strategy_process(strategy_id):
    """Stop a running strategy process - cross-platform implementation"""
    with PROCESS_LOCK:
        if strategy_id not in RUNNING_STRATEGIES:
            if strategy_id in STRATEGY_CONFIGS:
                pid = STRATEGY_CONFIGS[strategy_id].get("pid")
                if pid and check_process_status(pid):
                    try:
                        terminate_process_cross_platform(pid)
                        STRATEGY_CONFIGS[strategy_id]["is_running"] = False
                        STRATEGY_CONFIGS[strategy_id]["pid"] = None
                        STRATEGY_CONFIGS[strategy_id]["last_stopped"] = get_ist_time().isoformat()
                        save_configs()
                        return True, "Strategy stopped"
                    except:
                        pass
            return False, "Strategy not running"

        try:
            strategy_info = RUNNING_STRATEGIES[strategy_id]
            process = strategy_info["process"]
            pid = strategy_info["pid"]

            if isinstance(process, subprocess.Popen):
                if IS_WINDOWS:
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
                        process.wait(timeout=2)
                else:
                    try:
                        try:
                            os.killpg(os.getpgid(pid), signal.SIGTERM)
                            process.wait(timeout=5)
                        except OSError:
                            process.terminate()
                            process.wait(timeout=5)
                    except (subprocess.TimeoutExpired, ProcessLookupError):
                        try:
                            try:
                                os.killpg(os.getpgid(pid), signal.SIGKILL)
                            except OSError:
                                process.kill()
                            process.wait(timeout=2)
                        except ProcessLookupError:
                            pass
            elif hasattr(process, "terminate"):
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            else:
                terminate_process_cross_platform(pid)

            close_log_handle_safely(strategy_info)
            del RUNNING_STRATEGIES[strategy_id]

            ist_now = get_ist_time()
            STRATEGY_CONFIGS[strategy_id]["is_running"] = False
            STRATEGY_CONFIGS[strategy_id]["last_stopped"] = ist_now.isoformat()
            STRATEGY_CONFIGS[strategy_id]["pid"] = None
            save_configs()

            status, status_message = get_schedule_status(STRATEGY_CONFIGS[strategy_id])
            broadcast_status_update(strategy_id, status, status_message)

            logger.info(f"Stopped strategy {strategy_id} at {ist_now.strftime('%H:%M:%S IST')}")

            try:
                cleanup_strategy_logs(strategy_id)
            except Exception as cleanup_err:
                logger.warning(f"Log cleanup failed for {strategy_id}: {cleanup_err}")

            return True, f"Strategy stopped at {ist_now.strftime('%H:%M:%S IST')}"

        except Exception as e:
            logger.error(f"Failed to stop strategy {strategy_id}: {e}")
            return False, f"Failed to stop strategy: {str(e)}"


def cleanup_dead_processes():
    """Clean up strategies with dead processes"""
    with PROCESS_LOCK:
        dead_strategies = []

        for strategy_id, info in list(RUNNING_STRATEGIES.items()):
            process = info["process"]
            is_dead = False

            if isinstance(process, subprocess.Popen):
                if process.poll() is not None:
                    is_dead = True
            elif hasattr(process, "is_running"):
                try:
                    if not process.is_running():
                        is_dead = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    is_dead = True
            else:
                try:
                    pid = info.get("pid")
                    if pid and not psutil.pid_exists(pid):
                        is_dead = True
                except:
                    is_dead = True

            if is_dead:
                dead_strategies.append(strategy_id)
                close_log_handle_safely(info)

        for strategy_id in dead_strategies:
            del RUNNING_STRATEGIES[strategy_id]
            if strategy_id in STRATEGY_CONFIGS:
                STRATEGY_CONFIGS[strategy_id]["is_running"] = False
                STRATEGY_CONFIGS[strategy_id]["pid"] = None

        configs_to_fix = []
        for strategy_id, config in STRATEGY_CONFIGS.items():
            if config.get("is_running") and strategy_id not in RUNNING_STRATEGIES:
                pid = config.get("pid")
                if pid:
                    if not psutil.pid_exists(pid):
                        configs_to_fix.append(strategy_id)
                        logger.info(f"Cleaning up stale is_running flag for {strategy_id} (PID {pid} not found)")
                else:
                    configs_to_fix.append(strategy_id)
                    logger.info(f"Cleaning up stale is_running flag for {strategy_id} (no PID)")

        for strategy_id in configs_to_fix:
            STRATEGY_CONFIGS[strategy_id]["is_running"] = False
            STRATEGY_CONFIGS[strategy_id]["pid"] = None

        if configs_to_fix:
            save_configs()

        if dead_strategies:
            save_configs()
            logger.info(f"Cleaned up {len(dead_strategies)} dead processes")


def is_trading_day() -> bool:
    """Check if today is a valid trading day (not weekend, not holiday)."""
    try:
        today = datetime.now(IST).date()
        if is_market_holiday(today, exchange="NSE"):
            logger.info(f"Today ({today}) is a market holiday or weekend - skipping scheduled strategy")
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking trading day status: {e}")
        return False


def is_within_market_hours() -> bool:
    """Check if current time is within market trading hours."""
    try:
        return is_market_open()
    except Exception as e:
        logger.error(f"Error checking market hours: {e}")
        return False


def get_market_status() -> dict:
    """Get detailed market status with reason for being closed."""
    try:
        now = datetime.now(IST)
        today = now.date()

        if today.weekday() >= 5:
            day_name = "Saturday" if today.weekday() == 5 else "Sunday"
            return {"is_open": False, "reason": "weekend", "message": f"Market closed - {day_name}", "day": day_name}

        if is_market_holiday(today):
            return {"is_open": False, "reason": "holiday", "message": "Market closed - Holiday"}

        status = get_market_hours_status()

        if status.get("any_market_open"):
            return {"is_open": True, "reason": None, "message": "Market is open"}

        current_ms = status.get("current_time_ms", 0)
        earliest_open = status.get("earliest_open_ms", 33300000)

        if current_ms < earliest_open:
            return {"is_open": False, "reason": "before_market", "message": "Market closed - Before market hours"}
        else:
            return {"is_open": False, "reason": "after_market", "message": "Market closed - After market hours"}

    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        return {"is_open": False, "reason": "error", "message": f"Error checking market status: {str(e)}"}


def is_trading_day_enforcement_enabled() -> bool:
    """Trading day enforcement is always enabled."""
    return True


def scheduled_start_strategy(strategy_id: str):
    """Wrapper function for scheduled strategy start."""
    config = STRATEGY_CONFIGS.get(strategy_id, {})
    now = datetime.now(IST)
    day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today_day = day_names[now.weekday()]

    if config.get("manually_stopped"):
        logger.info(f"Strategy {strategy_id} was manually stopped - skipping scheduled auto-start")
        return

    schedule_days = config.get("schedule_days", [])
    today_in_schedule = today_day in [d.lower() for d in schedule_days]

    if today_in_schedule:
        logger.info(f"Strategy {strategy_id} is explicitly scheduled for {today_day.capitalize()} - skipping trading day check")
    else:
        logger.warning(f"Strategy {strategy_id} scheduled start called but {today_day.capitalize()} not in schedule_days")
        return

    if is_trading_day_enforcement_enabled() and now.weekday() < 5:
        if not is_trading_day():
            reason = "holiday"
            message = "Market closed - Holiday"
            logger.warning(f"Strategy {strategy_id} scheduled start BLOCKED - {message}")

            if strategy_id in STRATEGY_CONFIGS:
                STRATEGY_CONFIGS[strategy_id]["paused_reason"] = reason
                STRATEGY_CONFIGS[strategy_id]["paused_message"] = message
                save_configs()
            return

    if strategy_id in STRATEGY_CONFIGS:
        STRATEGY_CONFIGS[strategy_id].pop("paused_reason", None)
        STRATEGY_CONFIGS[strategy_id].pop("paused_message", None)

    logger.info(f"All checks passed - proceeding to start strategy {strategy_id}")
    start_strategy_process(strategy_id)


def scheduled_stop_strategy(strategy_id: str):
    """Wrapper function for scheduled strategy stop."""
    logger.info(f"Scheduled stop triggered for strategy {strategy_id}")
    stop_strategy_process(strategy_id)


def daily_trading_day_check():
    """Daily check that runs at 00:01 IST to stop scheduled strategies on non-trading days."""
    try:
        if not is_trading_day_enforcement_enabled():
            logger.debug("Market hours enforcement is disabled - skipping daily check")
            return

        market_status = get_market_status()

        if market_status["is_open"]:
            logger.debug("Daily check: Market is open - no cleanup needed")
            return

        reason = market_status["reason"]
        message = market_status["message"]

        logger.info(f"Daily check: {message} - checking for running scheduled strategies")

        now = datetime.now(IST)
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        today_day = day_names[now.weekday()]

        stopped_count = 0
        for strategy_id, config in list(STRATEGY_CONFIGS.items()):
            if not config.get("is_scheduled"):
                continue

            schedule_days = config.get("schedule_days", [])
            if today_day in [d.lower() for d in schedule_days]:
                logger.debug(f"Strategy {strategy_id} scheduled for {today_day} - not stopping")
                continue

            is_running = strategy_id in RUNNING_STRATEGIES
            if not is_running and config.get("is_running"):
                pid = config.get("pid")
                if pid and check_process_status(pid):
                    is_running = True

            if is_running:
                logger.info(f"Stopping scheduled strategy {strategy_id} - {message}")
                stop_strategy_process(strategy_id)

                STRATEGY_CONFIGS[strategy_id]["paused_reason"] = reason
                STRATEGY_CONFIGS[strategy_id]["paused_message"] = message
                stopped_count += 1

        if stopped_count > 0:
            save_configs()
            logger.info(f"Daily cleanup: Stopped {stopped_count} scheduled strategies ({message})")
        else:
            logger.debug("Daily cleanup: No scheduled strategies were running")

    except Exception as e:
        logger.error(f"Error in daily trading day check: {e}")


def is_within_schedule_time(strategy_id: str) -> bool:
    """Check if current time is within the strategy's scheduled time range."""
    try:
        config = STRATEGY_CONFIGS.get(strategy_id, {})
        schedule_start = config.get("schedule_start")
        schedule_stop = config.get("schedule_stop")

        if not schedule_start:
            return False

        now = datetime.now(IST)
        current_time = now.time()

        start_hour, start_min = map(int, schedule_start.split(":"))
        start_time = time(start_hour, start_min)

        if schedule_stop:
            stop_hour, stop_min = map(int, schedule_stop.split(":"))
            stop_time = time(stop_hour, stop_min)
        else:
            stop_time = time(23, 59)

        return start_time <= current_time <= stop_time

    except Exception as e:
        logger.error(f"Error checking schedule time for {strategy_id}: {e}")
        return False


def market_hours_enforcer():
    """Periodic check that runs every minute to enforce TRADING DAYS only."""
    try:
        if not is_trading_day_enforcement_enabled():
            return

        today_is_trading_day = is_trading_day()

        if today_is_trading_day:
            started_count = 0
            cleared_any = False

            for strategy_id, config in list(STRATEGY_CONFIGS.items()):
                paused_reason = config.get("paused_reason")

                if paused_reason in ("weekend", "holiday") and config.get("is_scheduled"):
                    is_running = strategy_id in RUNNING_STRATEGIES
                    if not is_running and config.get("pid"):
                        is_running = check_process_status(config.get("pid"))

                    if not is_running:
                        if is_within_schedule_time(strategy_id):
                            logger.info(f"Trading day enforcer: Starting paused strategy {strategy_id} (was: {paused_reason})")
                            success, message = start_strategy_process(strategy_id)
                            if success:
                                started_count += 1
                            else:
                                logger.warning(f"Failed to start {strategy_id}: {message}")

                if "paused_reason" in config:
                    del config["paused_reason"]
                    cleared_any = True
                if "paused_message" in config:
                    del config["paused_message"]
                    cleared_any = True

            if cleared_any or started_count > 0:
                save_configs()
                if started_count > 0:
                    logger.info(f"Trading day enforcer: Started {started_count} paused strategies")
            return

        now = datetime.now(IST)
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        today_day = day_names[now.weekday()]

        if now.weekday() >= 5:
            reason = "weekend"
            day_name = "Saturday" if now.weekday() == 5 else "Sunday"
            message = f"Market closed - {day_name}"
        else:
            reason = "holiday"
            message = "Market closed - Holiday"

        stopped_count = 0
        for strategy_id, config in list(STRATEGY_CONFIGS.items()):
            if not config.get("is_scheduled"):
                continue

            schedule_days = config.get("schedule_days", [])
            if today_day in [d.lower() for d in schedule_days]:
                logger.debug(f"Strategy {strategy_id} scheduled for {today_day} - not stopping")
                continue

            is_running = strategy_id in RUNNING_STRATEGIES
            if not is_running and config.get("is_running"):
                pid = config.get("pid")
                if pid and check_process_status(pid):
                    is_running = True

            if is_running:
                logger.info(f"Trading day enforcer: Stopping {strategy_id} - {message}")
                stop_strategy_process(strategy_id)

                STRATEGY_CONFIGS[strategy_id]["paused_reason"] = reason
                STRATEGY_CONFIGS[strategy_id]["paused_message"] = message
                stopped_count += 1

        if stopped_count > 0:
            save_configs()
            logger.info(f"Trading day enforcer: Stopped {stopped_count} strategies ({message})")

    except Exception as e:
        logger.error(f"Error in trading day enforcer: {e}")


def cleanup_strategy_logs(strategy_id: str):
    """Cleanup log files for a strategy based on configured limits."""
    if strategy_id in RUNNING_STRATEGIES:
        return

    try:
        max_files = int(os.getenv("STRATEGY_LOG_MAX_FILES", "10"))
        max_size_mb = float(os.getenv("STRATEGY_LOG_MAX_SIZE_MB", "50"))
        retention_days = int(os.getenv("STRATEGY_LOG_RETENTION_DAYS", "7"))

        log_files = sorted(LOGS_DIR.glob(f"{strategy_id}_*.log"), key=lambda f: f.stat().st_mtime)

        if not log_files:
            return

        now = datetime.now(IST)
        deleted_count = 0

        for log_file in log_files[:]:
            try:
                file_age_days = (now - datetime.fromtimestamp(log_file.stat().st_mtime, tz=IST)).days
                if file_age_days > retention_days:
                    log_file.unlink()
                    log_files.remove(log_file)
                    deleted_count += 1
                    logger.debug(f"Deleted old log file {log_file.name} ({file_age_days} days old)")
            except Exception as e:
                logger.error(f"Error deleting old log {log_file.name}: {e}")

        while len(log_files) > max_files:
            try:
                oldest = log_files.pop(0)
                oldest.unlink()
                deleted_count += 1
                logger.debug(f"Deleted log file {oldest.name} (exceeds max files: {max_files})")
            except Exception as e:
                logger.error(f"Error deleting log {oldest.name}: {e}")
                break

        total_size_mb = sum(f.stat().st_size for f in log_files) / (1024 * 1024)
        while total_size_mb > max_size_mb and log_files:
            try:
                oldest = log_files.pop(0)
                file_size_mb = oldest.stat().st_size / (1024 * 1024)
                oldest.unlink()
                total_size_mb -= file_size_mb
                deleted_count += 1
                logger.debug(f"Deleted log file {oldest.name} (exceeds max size: {max_size_mb}MB)")
            except Exception as e:
                logger.error(f"Error deleting log {oldest.name}: {e}")
                break

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} log files for strategy {strategy_id}")

    except Exception as e:
        logger.error(f"Error cleaning up logs for strategy {strategy_id}: {e}")


def schedule_strategy(strategy_id, start_time, stop_time=None, days=None):
    """Schedule a strategy to run at specific times (IST)."""
    if not days:
        days = ["mon", "tue", "wed", "thu", "fri"]

    valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    days_lower = [d.lower() for d in days]
    invalid_days = set(days_lower) - valid_days
    if invalid_days:
        raise ValueError(f"Invalid schedule days: {invalid_days}. Valid days: mon, tue, wed, thu, fri, sat, sun")

    days = days_lower

    start_job_id = f"start_{strategy_id}"
    stop_job_id = f"stop_{strategy_id}"

    if SCHEDULER.get_job(start_job_id):
        SCHEDULER.remove_job(start_job_id)
    if SCHEDULER.get_job(stop_job_id):
        SCHEDULER.remove_job(stop_job_id)

    hour, minute = map(int, start_time.split(":"))
    SCHEDULER.add_job(
        func=lambda: scheduled_start_strategy(strategy_id),
        trigger=CronTrigger(hour=hour, minute=minute, day_of_week=",".join(days), timezone=IST),
        id=start_job_id,
        replace_existing=True,
    )

    if stop_time:
        hour, minute = map(int, stop_time.split(":"))
        SCHEDULER.add_job(
            func=lambda: scheduled_stop_strategy(strategy_id),
            trigger=CronTrigger(hour=hour, minute=minute, day_of_week=",".join(days), timezone=IST),
            id=stop_job_id,
            replace_existing=True,
        )

    STRATEGY_CONFIGS[strategy_id]["is_scheduled"] = True
    STRATEGY_CONFIGS[strategy_id]["schedule_start"] = start_time
    STRATEGY_CONFIGS[strategy_id]["schedule_stop"] = stop_time
    STRATEGY_CONFIGS[strategy_id]["schedule_days"] = days
    save_configs()

    logger.info(f"Scheduled strategy {strategy_id}: {start_time} - {stop_time} IST on {days}")


def unschedule_strategy(strategy_id):
    """Remove scheduling for a strategy"""
    start_job_id = f"start_{strategy_id}"
    stop_job_id = f"stop_{strategy_id}"

    if SCHEDULER.get_job(start_job_id):
        SCHEDULER.remove_job(start_job_id)
    if SCHEDULER.get_job(stop_job_id):
        SCHEDULER.remove_job(stop_job_id)

    if strategy_id in STRATEGY_CONFIGS:
        STRATEGY_CONFIGS[strategy_id]["is_scheduled"] = False
        save_configs()

    logger.info(f"Unscheduled strategy {strategy_id}")


def get_schedule_status(config):
    """Determine detailed schedule status for a strategy."""
    now = datetime.now(IST)
    day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today_day = day_names[now.weekday()]
    current_time = now.strftime("%H:%M")

    schedule_days = config.get("schedule_days", [])
    schedule_start = config.get("schedule_start", "09:00")
    schedule_stop = config.get("schedule_stop", "16:00")
    schedule_days_lower = [d.lower() for d in schedule_days]

    if config.get("manually_stopped"):
        return "manually_stopped", "Manually stopped - click Start to resume"

    paused_reason = config.get("paused_reason")
    if paused_reason == "holiday":
        return "paused", config.get("paused_message", "Market Holiday")

    if schedule_days and today_day not in schedule_days_lower:
        next_days = ", ".join([d.capitalize() for d in schedule_days[:3]])
        if len(schedule_days) > 3:
            next_days += "..."
        return "scheduled", f"Next: {next_days} at {schedule_start} IST"

    if schedule_start and schedule_stop:
        if current_time < schedule_start:
            return "scheduled", f"Starts today at {schedule_start} IST"
        elif current_time > schedule_stop:
            return "scheduled", f"Next scheduled day at {schedule_start} IST"

    return "scheduled", f"Active window: {schedule_start} - {schedule_stop} IST"


_initialized = False


def initialize_with_app_context():
    """Initialize components that require app context/database access"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    try:
        for strategy_id, config in STRATEGY_CONFIGS.items():
            if config.get("is_scheduled"):
                start_time = config.get("schedule_start")
                stop_time = config.get("schedule_stop")
                days = config.get("schedule_days", ["mon", "tue", "wed", "thu", "fri"])
                if start_time:
                    try:
                        schedule_strategy(strategy_id, start_time, stop_time, days)
                        logger.info(f"Restored schedule for strategy {strategy_id} at {start_time} IST")
                    except Exception as e:
                        logger.error(f"Failed to restore schedule for {strategy_id}: {e}")

        daily_trading_day_check()

        logger.info(f"Python Strategy System fully initialized on {OS_TYPE}")
    except Exception as e:
        logger.warning(f"Deferred initialization skipped (likely no app context yet): {e}")
        _initialized = False


def cleanup_on_exit():
    """Clean up all running processes on application exit"""
    logger.info("Cleaning up running strategies...")
    with PROCESS_LOCK:
        for strategy_id in list(RUNNING_STRATEGIES.keys()):
            try:
                stop_strategy_process(strategy_id)
            except:
                pass
    logger.info("Cleanup complete")


atexit.register(cleanup_on_exit)
ensure_directories()
load_configs()
init_scheduler()


# =============================================================================
# FastAPI Routes
# =============================================================================


@python_strategy_router.get("/")
async def index(request: Request, session: dict = Depends(get_session)):
    """Main dashboard"""
    from utils.session import is_session_valid
    if not is_session_valid():
        return RedirectResponse(url="/auth/login", status_code=302)

    initialize_with_app_context()
    cleanup_dead_processes()

    strategies = []
    for sid, config in STRATEGY_CONFIGS.items():
        if config.get("pid"):
            config["is_running"] = check_process_status(config["pid"])
            if not config["is_running"]:
                config["pid"] = None
                save_configs()

        strategy_info = {
            "id": sid,
            "name": config.get("name", "Unnamed"),
            "file": Path(config.get("file_path", "")).name,
            "is_running": config.get("is_running", False),
            "is_scheduled": config.get("is_scheduled", False),
            "is_error": config.get("is_error", False),
            "error_message": config.get("error_message", ""),
            "error_time": format_ist_time(config.get("error_time", "")),
            "schedule_start": config.get("schedule_start", ""),
            "schedule_stop": config.get("schedule_stop", ""),
            "schedule_days": config.get("schedule_days", []),
            "created_at": config.get("created_at", ""),
            "last_started": format_ist_time(config.get("last_started", "")),
            "last_stopped": format_ist_time(config.get("last_stopped", "")),
            "pid": config.get("pid"),
            "params": {},
        }

        if sid in RUNNING_STRATEGIES:
            info = RUNNING_STRATEGIES[sid]
            strategy_info["started_at"] = info["started_at"]
            strategy_info["log_file"] = info["log_file"]

        strategies.append(strategy_info)

    current_ist = get_ist_time().strftime("%Y-%m-%d %H:%M:%S IST")

    return templates.TemplateResponse(
        "python_strategy/index.html",
        {"request": request, "strategies": strategies, "current_ist_time": current_ist, "platform": OS_TYPE.capitalize()},
    )


@python_strategy_router.get("/new")
async def new_strategy_get(request: Request, session: dict = Depends(check_session_validity)):
    """Upload a new strategy - GET"""
    return templates.TemplateResponse("python_strategy/new.html", {"request": request})


@python_strategy_router.post("/new")
async def new_strategy_post(
    request: Request,
    strategy_file: UploadFile = File(...),
    strategy_name: str = Form(""),
    schedule_start: str = Form("09:00"),
    schedule_stop: str = Form("16:00"),
    schedule_days: str = Form('["mon","tue","wed","thu","fri"]'),
    session: dict = Depends(check_session_validity),
):
    """Upload a new strategy - POST"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    if not strategy_file.filename:
        return JSONResponse({"status": "error", "message": "No file selected"}, status_code=400)

    if not strategy_file.filename.endswith(".py"):
        return JSONResponse({"status": "error", "message": "Please upload a Python (.py) file"}, status_code=400)

    safe_filename = secure_filename(strategy_file.filename)
    if not safe_filename or not safe_filename.endswith(".py"):
        return JSONResponse({"status": "error", "message": "Invalid filename"}, status_code=400)

    ist_now = get_ist_time()
    safe_stem = Path(safe_filename).stem
    safe_stem = "".join(c for c in safe_stem if c.isalnum() or c in "_-")
    if not safe_stem:
        safe_stem = "strategy"
    strategy_id = f"{safe_stem}_{ist_now.strftime('%Y%m%d%H%M%S')}"

    file_path = STRATEGIES_DIR / f"{strategy_id}.py"

    try:
        resolved_path = file_path.resolve()
        strategies_dir_resolved = STRATEGIES_DIR.resolve()
        if not str(resolved_path).startswith(str(strategies_dir_resolved)):
            logger.warning(f"Path traversal attempt in file upload: {strategy_file.filename}")
            return JSONResponse({"status": "error", "message": "Invalid file path"}, status_code=400)
    except Exception as e:
        logger.error(f"Error validating file path: {e}")
        return JSONResponse({"status": "error", "message": "Invalid file path"}, status_code=400)

    STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
    content = await strategy_file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    if not IS_WINDOWS:
        try:
            os.chmod(file_path, 0o755)
        except:
            pass

    if not strategy_name:
        strategy_name = safe_stem
    strategy_name = strategy_name.strip()[:100]

    try:
        schedule_days_list = json.loads(schedule_days)
        if not isinstance(schedule_days_list, list):
            schedule_days_list = ["mon", "tue", "wed", "thu", "fri"]
    except (json.JSONDecodeError, TypeError):
        schedule_days_list = ["mon", "tue", "wed", "thu", "fri"]

    if not schedule_start:
        schedule_start = "09:00"
    if not schedule_stop:
        schedule_stop = "16:00"
    if not schedule_days_list:
        schedule_days_list = ["mon", "tue", "wed", "thu", "fri"]

    STRATEGY_CONFIGS[strategy_id] = {
        "name": strategy_name,
        "file_path": str(file_path),
        "file_name": f"{strategy_id}.py",
        "is_running": False,
        "is_scheduled": True,
        "created_at": ist_now.isoformat(),
        "user_id": user_id,
        "schedule_start": schedule_start,
        "schedule_stop": schedule_stop,
        "schedule_days": schedule_days_list,
    }
    save_configs()

    try:
        schedule_strategy(strategy_id, schedule_start, schedule_stop, schedule_days_list)
    except Exception as e:
        logger.error(f"Failed to schedule strategy {strategy_id}: {e}")

    return JSONResponse({
        "status": "success",
        "message": f'Strategy "{strategy_name}" uploaded successfully',
        "data": {"strategy_id": strategy_id},
    })


@python_strategy_router.post("/start/{strategy_id}")
async def start_strategy(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Start a strategy"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    is_owner, error_response = verify_strategy_ownership(strategy_id, user_id)
    if not is_owner:
        return error_response

    config = STRATEGY_CONFIGS.get(strategy_id, {})
    if not config.get("is_scheduled"):
        logger.info(f"Auto-enabling scheduler for legacy strategy {strategy_id}")
        config["is_scheduled"] = True
        config["schedule_start"] = config.get("schedule_start", "09:00")
        config["schedule_stop"] = config.get("schedule_stop", "16:00")
        config["schedule_days"] = config.get("schedule_days", ["mon", "tue", "wed", "thu", "fri"])
        STRATEGY_CONFIGS[strategy_id] = config
        save_configs()
        schedule_strategy(strategy_id, config.get("schedule_start"), config.get("schedule_stop"), config.get("schedule_days"))

    if strategy_id in STRATEGY_CONFIGS and STRATEGY_CONFIGS[strategy_id].get("manually_stopped"):
        STRATEGY_CONFIGS[strategy_id].pop("manually_stopped", None)
        save_configs()
        logger.info(f"Cleared manual stop flag for strategy {strategy_id}")

    schedule_days = config.get("schedule_days", [])
    now = datetime.now(IST)
    day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today_day = day_names[now.weekday()]

    schedule_start = config.get("schedule_start")
    schedule_stop = config.get("schedule_stop")

    is_scheduled_day = today_day in [d.lower() for d in schedule_days] if schedule_days else True
    is_within_hours = True

    if schedule_start and schedule_stop:
        try:
            start_hour, start_min = map(int, schedule_start.split(":"))
            stop_hour, stop_min = map(int, schedule_stop.split(":"))
            start_time = now.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            stop_time = now.replace(hour=stop_hour, minute=stop_min, second=0, microsecond=0)
            is_within_hours = start_time <= now <= stop_time
        except (ValueError, AttributeError) as e:
            logger.warning(f"Could not parse schedule times for {strategy_id}: {e}")

    is_holiday = not is_trading_day() and now.weekday() < 5

    if not is_scheduled_day or not is_within_hours or is_holiday:
        if is_holiday:
            reason = "Market holiday"
            next_start = f"next trading day at {schedule_start} IST"
        elif not is_scheduled_day:
            reason = f"Today ({today_day.capitalize()}) is not in schedule"
            next_days = [d for d in schedule_days]
            next_start = f"next scheduled day ({', '.join(next_days)}) at {schedule_start} IST"
        else:
            reason = f"Outside schedule hours ({schedule_start} - {schedule_stop} IST)"
            if now < start_time:
                next_start = f"today at {schedule_start} IST"
            else:
                next_start = f"next scheduled day at {schedule_start} IST"

        logger.info(f"Strategy {strategy_id} armed for scheduled start. Reason: {reason}. Next start: {next_start}")

        return JSONResponse({
            "status": "success",
            "message": f"Strategy armed for scheduled start. {reason}. Will start {next_start}.",
            "data": {"armed": True, "reason": reason, "next_start": next_start},
        })

    initialize_with_app_context()
    success, message = start_strategy_process(strategy_id)
    return JSONResponse({"status": "success" if success else "error", "message": message})


@python_strategy_router.post("/stop/{strategy_id}")
async def stop_strategy(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Stop a strategy manually or cancel a scheduled auto-start"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    is_owner, error_response = verify_strategy_ownership(strategy_id, user_id)
    if not is_owner:
        return error_response

    config = STRATEGY_CONFIGS.get(strategy_id, {})
    is_running = config.get("is_running", False)

    if is_running:
        success, message = stop_strategy_process(strategy_id)
        if success and strategy_id in STRATEGY_CONFIGS:
            STRATEGY_CONFIGS[strategy_id]["manually_stopped"] = True
            save_configs()
            logger.info(f"Strategy {strategy_id} manually stopped")
        return JSONResponse({"status": "success" if success else "error", "message": message})
    else:
        if strategy_id in STRATEGY_CONFIGS:
            STRATEGY_CONFIGS[strategy_id]["manually_stopped"] = True
            save_configs()
            logger.info(f"Strategy {strategy_id} schedule cancelled")
            return JSONResponse({"status": "success", "message": "Scheduled auto-start cancelled"})
        else:
            return JSONResponse({"status": "error", "message": "Strategy not found"}, status_code=404)


@python_strategy_router.post("/schedule/{strategy_id}")
async def schedule_strategy_route(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Schedule a strategy"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    is_owner, result = verify_strategy_ownership(strategy_id, user_id, return_config=True)
    if not is_owner:
        return result

    config = result
    if config.get("is_running", False):
        return JSONResponse({
            "status": "error",
            "message": "Cannot modify schedule while strategy is running. Please stop the strategy first.",
            "error_code": "STRATEGY_RUNNING",
        }, status_code=400)

    data = await request.json()
    start_time = data.get("start_time")
    stop_time = data.get("stop_time")
    days = data.get("days", ["mon", "tue", "wed", "thu", "fri"])

    if not start_time:
        return JSONResponse({"status": "error", "message": "Start time is required"}, status_code=400)

    try:
        schedule_strategy(strategy_id, start_time, stop_time, days)
        schedule_info = f"Scheduled at {start_time} IST"
        if stop_time:
            schedule_info += f" - {stop_time} IST"
        return JSONResponse({"status": "success", "message": schedule_info})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@python_strategy_router.post("/unschedule/{strategy_id}")
async def unschedule_strategy_route(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Remove scheduling for a strategy - DISABLED: scheduler is mandatory"""
    return JSONResponse({
        "status": "error",
        "message": "Scheduler is mandatory and cannot be disabled. You can only modify the schedule times and days.",
    }, status_code=400)


@python_strategy_router.post("/delete/{strategy_id}")
async def delete_strategy(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Delete a strategy"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    is_owner, error_response = verify_strategy_ownership(strategy_id, user_id)
    if not is_owner:
        return error_response

    with PROCESS_LOCK:
        if strategy_id in RUNNING_STRATEGIES or (strategy_id in STRATEGY_CONFIGS and STRATEGY_CONFIGS[strategy_id].get("is_running")):
            stop_strategy_process(strategy_id)

        if STRATEGY_CONFIGS.get(strategy_id, {}).get("is_scheduled"):
            unschedule_strategy(strategy_id)

        if strategy_id in STRATEGY_CONFIGS:
            file_path = Path(STRATEGY_CONFIGS[strategy_id].get("file_path", ""))
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.error(f"Failed to delete file {file_path}: {e}")

            del STRATEGY_CONFIGS[strategy_id]
            save_configs()

            return JSONResponse({"status": "success", "message": "Strategy deleted successfully"})

        return JSONResponse({"status": "error", "message": "Strategy not found"})


@python_strategy_router.get("/logs/{strategy_id}")
async def view_logs(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """View strategy logs"""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    is_owner, error_response = verify_strategy_ownership(strategy_id, user_id)
    if not is_owner:
        return RedirectResponse(url="/python", status_code=302)

    log_files = []

    try:
        for log_file in LOGS_DIR.glob(f"{strategy_id}_*.log"):
            log_files.append({
                "name": log_file.name,
                "size": log_file.stat().st_size,
                "modified": datetime.fromtimestamp(log_file.stat().st_mtime, tz=IST),
            })
    except Exception as e:
        logger.error(f"Error reading log files: {e}")

    log_files.sort(key=lambda x: x["modified"], reverse=True)

    log_content = None
    if log_files and request.query_params.get("latest"):
        latest_log = LOGS_DIR / log_files[0]["name"]
        try:
            with open(latest_log, encoding="utf-8", errors="ignore") as f:
                log_content = f.read()
        except Exception as e:
            log_content = f"Error reading log file: {e}"

    return templates.TemplateResponse(
        "python_strategy/logs.html",
        {"request": request, "strategy_id": strategy_id, "log_files": log_files, "log_content": log_content},
    )


@python_strategy_router.post("/logs/{strategy_id}/clear")
async def clear_logs(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Clear all log files for a strategy"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    is_owner, error_response = verify_strategy_ownership(strategy_id, user_id)
    if not is_owner:
        return error_response

    try:
        if strategy_id in RUNNING_STRATEGIES:
            return JSONResponse({
                "status": "error",
                "message": "Cannot clear logs while strategy is running. Please stop the strategy first.",
            }, status_code=400)

        cleared_count = 0
        total_size = 0

        log_files = list(LOGS_DIR.glob(f"{strategy_id}_*.log"))

        if not log_files:
            return JSONResponse({"status": "error", "message": "No log files found to clear"}, status_code=404)

        for log_file in log_files:
            try:
                total_size += log_file.stat().st_size
            except:
                pass

        for log_file in log_files:
            try:
                log_file.unlink()
                logger.info(f"Deleted log file: {log_file.name}")
                cleared_count += 1
            except Exception as e:
                logger.error(f"Error clearing log file {log_file.name}: {e}")

        if cleared_count > 0:
            size_mb = total_size / (1024 * 1024)
            logger.info(f"Cleared {cleared_count} log files for strategy {strategy_id} ({size_mb:.2f} MB)")
            return JSONResponse({
                "status": "success",
                "message": f"Cleared {cleared_count} log files ({size_mb:.2f} MB)",
                "cleared_count": cleared_count,
                "total_size_mb": round(size_mb, 2),
            })
        else:
            return JSONResponse({"status": "error", "message": "No log files were cleared"}, status_code=500)

    except Exception as e:
        logger.error(f"Error clearing logs for strategy {strategy_id}: {e}")
        return JSONResponse({"status": "error", "message": f"Error clearing logs: {str(e)}"}, status_code=500)


@python_strategy_router.post("/clear-error/{strategy_id}")
async def clear_error_state(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Clear error state for a strategy"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    is_owner, result = verify_strategy_ownership(strategy_id, user_id, return_config=True)
    if not is_owner:
        return result

    config = result

    if config.get("is_running"):
        return JSONResponse({"status": "error", "message": "Cannot clear error state while strategy is running"}, status_code=400)

    if not config.get("is_error"):
        return JSONResponse({"status": "error", "message": "Strategy is not in error state"}, status_code=400)

    try:
        config.pop("is_error", None)
        config.pop("error_message", None)
        config.pop("error_time", None)
        save_configs()

        logger.info(f"Cleared error state for strategy {strategy_id}")
        return JSONResponse({"status": "success", "message": "Error state cleared successfully"})

    except Exception as e:
        logger.error(f"Failed to clear error state for {strategy_id}: {e}")
        return JSONResponse({"status": "error", "message": f"Failed to clear error state: {str(e)}"}, status_code=500)


@python_strategy_router.get("/status")
async def status(request: Request, session: dict = Depends(check_session_validity)):
    """Get system status"""
    cleanup_dead_processes()

    contracts_ready, contract_message = check_master_contract_ready()

    return JSONResponse({
        "running": len(RUNNING_STRATEGIES),
        "total": len(STRATEGY_CONFIGS),
        "scheduler_running": SCHEDULER is not None and SCHEDULER.running,
        "current_ist_time": get_ist_time().strftime("%H:%M:%S IST"),
        "platform": OS_TYPE,
        "master_contracts_ready": contracts_ready,
        "master_contracts_message": contract_message,
        "strategies": [
            {"id": sid, "name": config.get("name"), "is_running": config.get("is_running", False), "is_scheduled": config.get("is_scheduled", False)}
            for sid, config in STRATEGY_CONFIGS.items()
        ],
    })


@python_strategy_router.post("/check-contracts")
async def check_contracts(request: Request, session: dict = Depends(check_session_validity)):
    """Check master contracts and start pending strategies"""
    try:
        contracts_ready, contract_message = check_master_contract_ready()
        return JSONResponse({"success": contracts_ready, "message": contract_message})
    except Exception as e:
        logger.error(f"Error checking contracts: {e}")
        return JSONResponse({"success": False, "message": f"Error checking contracts: {str(e)}"}, status_code=500)


# =============================================================================
# JSON API Endpoints for React Frontend
# =============================================================================


@python_strategy_router.get("/api/strategies")
async def api_get_strategies(request: Request, session: dict = Depends(check_session_validity)):
    """API: Get all strategies as JSON"""
    cleanup_dead_processes()
    strategies = []

    for strategy_id, config in STRATEGY_CONFIGS.items():
        if config.get("is_running"):
            status = "running"
            status_message = "Running"
        elif config.get("error_message"):
            status = "error"
            status_message = config.get("error_message")
        else:
            status, status_message = get_schedule_status(config)

        strategies.append({
            "id": strategy_id,
            "name": config.get("name", ""),
            "file_name": config.get("file_name", ""),
            "status": status,
            "status_message": status_message,
            "is_running": config.get("is_running", False),
            "is_scheduled": config.get("is_scheduled", False),
            "manually_stopped": config.get("manually_stopped", False),
            "schedule_start_time": config.get("schedule_start"),
            "schedule_stop_time": config.get("schedule_stop"),
            "schedule_days": config.get("schedule_days", []),
            "last_started": config.get("last_started"),
            "last_stopped": config.get("last_stopped"),
            "error_message": config.get("error_message"),
            "paused_reason": config.get("paused_reason"),
            "paused_message": config.get("paused_message"),
            "process_id": config.get("process_id"),
            "created_at": config.get("created_at"),
        })

    return JSONResponse({"strategies": strategies})


@python_strategy_router.get("/api/events")
async def api_strategy_events(request: Request):
    """SSE endpoint for real-time strategy status updates"""
    def event_stream():
        q = queue.Queue(maxsize=100)

        with SSE_LOCK:
            SSE_SUBSCRIBERS.append(q)

        try:
            yield 'data: {"type": "connected"}\n\n'

            while True:
                try:
                    event = q.get(timeout=30)
                    yield event
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with SSE_LOCK:
                if q in SSE_SUBSCRIBERS:
                    SSE_SUBSCRIBERS.remove(q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@python_strategy_router.get("/api/strategy/{strategy_id}")
async def api_get_strategy(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """API: Get single strategy as JSON"""
    if strategy_id not in STRATEGY_CONFIGS:
        return JSONResponse({"status": "error", "message": "Strategy not found"}, status_code=404)

    config = STRATEGY_CONFIGS[strategy_id]

    if config.get("is_running"):
        status = "running"
        status_message = "Running"
    elif config.get("error_message"):
        status = "error"
        status_message = config.get("error_message")
    else:
        status, status_message = get_schedule_status(config)

    return JSONResponse({
        "strategy": {
            "id": strategy_id,
            "status_message": status_message,
            "manually_stopped": config.get("manually_stopped", False),
            "name": config.get("name", ""),
            "file_name": config.get("file_name", ""),
            "status": status,
            "is_running": config.get("is_running", False),
            "is_scheduled": config.get("is_scheduled", False),
            "schedule_start_time": config.get("schedule_start"),
            "schedule_stop_time": config.get("schedule_stop"),
            "schedule_days": config.get("schedule_days", []),
            "last_started": config.get("last_started"),
            "last_stopped": config.get("last_stopped"),
            "error_message": config.get("error_message"),
            "paused_reason": config.get("paused_reason"),
            "paused_message": config.get("paused_message"),
            "process_id": config.get("process_id"),
            "created_at": config.get("created_at"),
        }
    })


@python_strategy_router.get("/api/strategy/{strategy_id}/content")
async def api_get_strategy_content(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """API: Get strategy file content"""
    if strategy_id not in STRATEGY_CONFIGS:
        return JSONResponse({"status": "error", "message": "Strategy not found"}, status_code=404)

    config = STRATEGY_CONFIGS[strategy_id]
    file_name = config.get("file_name")
    file_path = config.get("file_path")

    if file_name:
        strategy_path = STRATEGIES_DIR / file_name
    elif file_path:
        strategy_path = Path(file_path)
        file_name = strategy_path.name
    else:
        return JSONResponse({"status": "error", "message": "Strategy file not found"}, status_code=404)

    if not strategy_path.exists():
        return JSONResponse({"status": "error", "message": "Strategy file not found on disk"}, status_code=404)

    try:
        content = strategy_path.read_text(encoding="utf-8")
        file_stats = strategy_path.stat()
        return JSONResponse({
            "name": config.get("name", ""),
            "file_name": file_name,
            "content": content,
            "is_running": config.get("is_running", False),
            "line_count": content.count("\n") + 1,
            "size_kb": file_stats.st_size / 1024,
            "last_modified": datetime.fromtimestamp(file_stats.st_mtime, tz=IST).isoformat(),
        })
    except Exception as e:
        logger.error(f"Error reading strategy file: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@python_strategy_router.get("/api/logs/{strategy_id}")
async def api_get_log_files(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """API: Get list of log files for a strategy"""
    if not strategy_id or ".." in strategy_id or "/" in strategy_id or "\\" in strategy_id:
        return JSONResponse({"status": "error", "message": "Invalid strategy ID"}, status_code=400)

    if strategy_id not in STRATEGY_CONFIGS:
        return JSONResponse({"status": "error", "message": "Strategy not found"}, status_code=404)

    logs = []
    try:
        for log_file in sorted(LOGS_DIR.glob(f"{strategy_id}_*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
            stats = log_file.stat()
            logs.append({
                "name": log_file.name,
                "size_kb": stats.st_size / 1024,
                "last_modified": datetime.fromtimestamp(stats.st_mtime, tz=IST).isoformat(),
            })
    except Exception as e:
        logger.error(f"Error listing log files for {strategy_id}: {e}")

    return JSONResponse({"logs": logs})


@python_strategy_router.get("/api/logs/{strategy_id}/{log_name}")
async def api_get_log_content(strategy_id: str, log_name: str, request: Request, session: dict = Depends(check_session_validity)):
    """API: Get log file content"""
    if not strategy_id or ".." in strategy_id or "/" in strategy_id or "\\" in strategy_id:
        return JSONResponse({"status": "error", "message": "Invalid strategy ID"}, status_code=400)

    if strategy_id not in STRATEGY_CONFIGS:
        return JSONResponse({"status": "error", "message": "Strategy not found"}, status_code=404)

    if not log_name or ".." in log_name or "/" in log_name or "\\" in log_name:
        return JSONResponse({"status": "error", "message": "Invalid log file name"}, status_code=400)

    if not log_name.startswith(f"{strategy_id}_"):
        return JSONResponse({"status": "error", "message": "Log file does not belong to this strategy"}, status_code=403)

    log_path = LOGS_DIR / log_name

    try:
        resolved_path = log_path.resolve()
        logs_dir_resolved = LOGS_DIR.resolve()
        if not str(resolved_path).startswith(str(logs_dir_resolved)):
            logger.warning(f"Path traversal attempt detected: {log_name}")
            return JSONResponse({"status": "error", "message": "Invalid log file path"}, status_code=403)
    except Exception as e:
        logger.error(f"Error resolving log path: {e}")
        return JSONResponse({"status": "error", "message": "Invalid log file path"}, status_code=400)

    if not log_path.exists():
        return JSONResponse({"status": "error", "message": "Log file not found"}, status_code=404)

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        stats = log_path.stat()
        line_count = content.count("\n") + 1 if content else 0
        return JSONResponse({
            "name": log_name,
            "content": content,
            "lines": line_count,
            "size_kb": stats.st_size / 1024,
            "last_updated": datetime.fromtimestamp(stats.st_mtime, tz=IST).isoformat(),
        })
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@python_strategy_router.get("/edit/{strategy_id}")
async def edit_strategy(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Edit or view a strategy file"""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    is_owner, error_response = verify_strategy_ownership(strategy_id, user_id)
    if not is_owner:
        return RedirectResponse(url="/python", status_code=302)

    config = STRATEGY_CONFIGS[strategy_id]
    file_path = Path(config["file_path"])

    if not file_path.exists():
        return RedirectResponse(url="/python", status_code=302)

    is_running = config.get("is_running", False)

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return RedirectResponse(url="/python", status_code=302)

    file_stats = file_path.stat()
    file_info = {
        "name": file_path.name,
        "size": file_stats.st_size,
        "modified": datetime.fromtimestamp(file_stats.st_mtime, tz=IST),
        "lines": content.count("\n") + 1,
    }

    return templates.TemplateResponse(
        "python_strategy/edit.html",
        {"request": request, "strategy_id": strategy_id, "strategy_name": config.get("name", "Unnamed Strategy"), "content": content, "is_running": is_running, "file_info": file_info, "can_edit": not is_running},
    )


@python_strategy_router.get("/export/{strategy_id}")
async def export_strategy(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Export/download a strategy file"""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    is_owner, error_response = verify_strategy_ownership(strategy_id, user_id)
    if not is_owner:
        return RedirectResponse(url="/python", status_code=302)

    config = STRATEGY_CONFIGS[strategy_id]
    file_path = Path(config["file_path"])

    if not file_path.exists():
        return RedirectResponse(url="/python", status_code=302)

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        logger.info(f"Strategy {strategy_id} exported successfully")
        return Response(
            content=content,
            media_type="text/x-python",
            headers={"Content-Disposition": f"attachment; filename={file_path.name}", "Content-Type": "text/x-python; charset=utf-8"},
        )

    except Exception as e:
        logger.error(f"Failed to export strategy {strategy_id}: {e}")
        return RedirectResponse(url="/python", status_code=302)


@python_strategy_router.post("/save/{strategy_id}")
async def save_strategy(strategy_id: str, request: Request, session: dict = Depends(check_session_validity)):
    """Save edited strategy file"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    is_owner, result = verify_strategy_ownership(strategy_id, user_id, return_config=True)
    if not is_owner:
        return result

    config = result

    if config.get("is_running", False):
        return JSONResponse({"status": "error", "message": "Cannot edit running strategy. Please stop it first."}, status_code=400)

    file_path = Path(config["file_path"])

    data = await request.json()
    if not data or "content" not in data:
        return JSONResponse({"status": "error", "message": "No content provided"}, status_code=400)

    new_content = data["content"]

    try:
        backup_path = file_path.with_suffix(".bak")
        if file_path.exists():
            with open(file_path, encoding="utf-8") as f:
                backup_content = f.read()
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(backup_content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        config["last_modified"] = get_ist_time().isoformat()
        save_configs()

        logger.info(f"Strategy {strategy_id} saved successfully")
        return JSONResponse({
            "status": "success",
            "message": "Strategy saved successfully",
            "timestamp": format_ist_time(config["last_modified"]),
        })

    except Exception as e:
        logger.error(f"Failed to save strategy {strategy_id}: {e}")
        return JSONResponse({"status": "error", "message": f"Failed to save: {str(e)}"}, status_code=500)
