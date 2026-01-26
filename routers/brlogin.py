# routers/brlogin.py
"""
FastAPI Broker Login Router for RealAlgo
Handles broker authentication callbacks.
Requirements: 4.7
"""

import json
import os
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from dependencies_fastapi import get_session
from limiter_fastapi import limiter
from utils.auth_utils_fastapi import handle_auth_failure_fastapi, handle_auth_success_fastapi
from utils.config import (
    get_broker_api_key,
    get_broker_api_secret,
    get_login_rate_limit_hour,
    get_login_rate_limit_min,
)
from utils.logging import get_logger

logger = get_logger(__name__)

BROKER_API_KEY = get_broker_api_key()
LOGIN_RATE_LIMIT_MIN = get_login_rate_limit_min()
LOGIN_RATE_LIMIT_HOUR = get_login_rate_limit_hour()

brlogin_router = APIRouter(prefix="", tags=["brlogin"])


def get_app_broker_auth_functions(request: Request):
    """Get broker auth functions from app state."""
    return request.app.state.broker_auth_functions


@brlogin_router.api_route("/{broker}/callback", methods=["GET", "POST"])
@limiter.limit(LOGIN_RATE_LIMIT_MIN)
@limiter.limit(LOGIN_RATE_LIMIT_HOUR)
async def broker_callback(broker: str, request: Request):
    """Handle broker authentication callbacks."""
    session = request.session
    logger.info(f"Broker callback initiated for: {broker}")
    logger.debug(f"Session contents: {dict(session)}")
    logger.info(f"Session has user key: {'user' in session}")

    # Special handling for Compositedge
    if broker == "compositedge" and "user" not in session:
        logger.info("Compositedge callback without session - will establish session after auth")
    elif broker == "mstock" and request.method == "POST" and "user" not in session:
        return RedirectResponse(url="/auth/broker-login", status_code=302)
    else:
        if "user" not in session:
            logger.warning(f"User not in session for {broker} callback, redirecting to login")
            return RedirectResponse(url="/auth/login", status_code=302)

    if session.get("logged_in"):
        session["broker"] = broker
        return RedirectResponse(url="/dashboard", status_code=302)

    broker_auth_functions = get_app_broker_auth_functions(request)
    auth_function = broker_auth_functions.get(f"{broker}_auth")

    if not auth_function:
        return JSONResponse({"error": "Broker authentication function not found."}, status_code=404)

    feed_token = None
    user_id = None
    auth_token = None
    error_message = None
    forward_url = "broker.html"

    # Handle different brokers
    if broker == "fivepaisa":
        if request.method == "GET":
            return RedirectResponse(url="/broker/fivepaisa/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            clientcode = form.get("userid") or form.get("clientid")
            broker_pin = form.get("pin")
            totp_code = form.get("totp")
            auth_token, error_message = auth_function(clientcode, broker_pin, totp_code)

    elif broker == "angel":
        if request.method == "GET":
            return RedirectResponse(url="/broker/angel/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            clientcode = form.get("userid") or form.get("clientid")
            broker_pin = form.get("pin")
            totp_code = form.get("totp")
            user_id = clientcode
            auth_token, feed_token, error_message = auth_function(clientcode, broker_pin, totp_code)

    elif broker == "mstock":
        if request.method == "GET":
            return RedirectResponse(url="/broker/mstock/totp", status_code=302)
        elif request.method == "POST":
            if "user" not in session:
                logger.error(f"mstock POST - Session lost!")
                return JSONResponse({"status": "error", "message": "Session expired. Please login again."}, status_code=401)

            from broker.mstock.api.auth_api import authenticate_with_totp
            form = await request.form()
            password = form.get("password")
            totp_code = form.get("totp")

            if not password:
                return JSONResponse({"status": "error", "message": "Password is required."}, status_code=400)
            if not totp_code:
                return JSONResponse({"status": "error", "message": "TOTP code is required."}, status_code=400)

            auth_token, feed_token, error_message = authenticate_with_totp(password, totp_code)

            if error_message:
                return JSONResponse({"status": "error", "message": error_message}, status_code=401)

            logger.info("mStock TOTP authentication successful")
            return handle_auth_success_fastapi(request, auth_token, session["user"], broker, feed_token=feed_token, user_id=None)

    elif broker == "aliceblue":
        if request.method == "GET":
            return RedirectResponse(url="/broker/aliceblue/totp", status_code=302)
        elif request.method == "POST":
            logger.info("Aliceblue Login Flow initiated")
            form = await request.form()
            userid = form.get("userid")

            from utils.httpx_client import get_httpx_client
            client = get_httpx_client()

            payload = {"userId": userid}
            headers = {"Content-Type": "application/json"}
            try:
                url = "https://ant.aliceblueonline.com/rest/AliceBlueAPIService/api/customer/getAPIEncpkey"
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data_dict = response.json()
                logger.debug(f"Aliceblue response data: {data_dict}")

                if data_dict.get("stat") == "Ok" and data_dict.get("encKey"):
                    enc_key = data_dict["encKey"]
                    auth_token, error_message = auth_function(userid, enc_key)

                    if auth_token:
                        return handle_auth_success_fastapi(request, auth_token, session["user"], broker)
                    else:
                        return handle_auth_failure_fastapi(request, error_message, forward_url="broker.html")
                else:
                    error_msg = data_dict.get("emsg", "Failed to get encryption key")
                    return handle_auth_failure_fastapi(request, f"Failed to get encryption key: {error_msg}", forward_url="broker.html")
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Authentication error: {str(e)}"}, status_code=500)

    elif broker == "fivepaisaxts":
        code = "fivepaisaxts"
        logger.debug(f"FivePaisaXTS broker - code: {code}")
        auth_token, feed_token, user_id, error_message = auth_function(code)

    elif broker == "compositedge":
        if "user" not in session:
            logger.warning("Session 'user' key missing in Compositedge callback, attempting to recover")

        try:
            if request.method == "POST":
                content_type = request.headers.get("Content-Type", "")
                if "application/x-www-form-urlencoded" in content_type:
                    raw_data = (await request.body()).decode("utf-8")
                    if raw_data.startswith("session="):
                        session_data = unquote(raw_data[8:])
                    else:
                        session_data = raw_data
                else:
                    session_data = (await request.body()).decode("utf-8")
            else:
                session_data = request.query_params.get("session")

            if not session_data:
                return JSONResponse({"error": "No session data received"}, status_code=400)

            try:
                if isinstance(session_data, str):
                    session_data = session_data.strip()
                    session_json = json.loads(session_data)
                    if isinstance(session_json, str):
                        session_json = json.loads(session_json)
                else:
                    session_json = session_data
            except json.JSONDecodeError as e:
                return JSONResponse({"error": f"Invalid JSON format: {str(e)}", "raw_data": session_data}, status_code=400)

            access_token = session_json.get("accessToken")
            if not access_token:
                return JSONResponse({"error": "No access token found"}, status_code=400)

            auth_token, feed_token, user_id, error_message = auth_function(access_token)

        except Exception as e:
            return JSONResponse({"error": f"Error processing request: {str(e)}"}, status_code=500)

    elif broker == "fyers":
        code = request.query_params.get("auth_code")
        logger.debug(f"Fyers broker - The code is {code}")
        auth_token, error_message = auth_function(code)

    elif broker == "tradejini":
        if request.method == "GET":
            return RedirectResponse(url="/broker/tradejini/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            password = form.get("password")
            twofa = form.get("twofa")
            twofatype = form.get("twofatype")

            auth_token, error_message = auth_function(password=password, twofa=twofa, twofa_type=twofatype)

            if auth_token:
                return handle_auth_success_fastapi(request, auth_token, session["user"], broker)
            else:
                return JSONResponse({"status": "error", "message": error_message}, status_code=401)

    elif broker == "icici":
        code = request.query_params.get("apisession")
        logger.debug(f"ICICI broker - The code is {code}")
        auth_token, error_message = auth_function(code)

    elif broker == "ibulls":
        code = "ibulls"
        auth_token, feed_token, user_id, error_message = auth_function(code)

    elif broker == "iifl":
        code = "iifl"
        auth_token, feed_token, user_id, error_message = auth_function(code)

    elif broker == "jainamxts":
        code = "jainamxts"
        auth_token, feed_token, user_id, error_message = auth_function(code)

    elif broker == "dhan":
        await _handle_dhan_callback(request, session, auth_function)
        return  # _handle_dhan_callback handles its own responses

    elif broker == "indmoney":
        code = "indmoney"
        auth_token, error_message = auth_function(code)

    elif broker == "dhan_sandbox":
        code = "dhan_sandbox"
        auth_token, error_message = auth_function(code)

    elif broker == "groww":
        code = "groww"
        auth_token, error_message = auth_function(code)

    elif broker == "wisdom":
        code = "wisdom"
        auth_token, feed_token, user_id, error_message = auth_function(code)

    elif broker == "zebu":
        if request.method == "GET":
            return RedirectResponse(url="/broker/zebu/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            userid = form.get("userid")
            password = form.get("password")
            totp_code = form.get("totp")
            auth_token, error_message = auth_function(userid, password, totp_code)

    elif broker == "shoonya":
        if request.method == "GET":
            return RedirectResponse(url="/broker/shoonya/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            userid = form.get("userid")
            password = form.get("password")
            totp_code = form.get("totp")
            auth_token, error_message = auth_function(userid, password, totp_code)

    elif broker == "firstock":
        if request.method == "GET":
            return RedirectResponse(url="/broker/firstock/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            userid = form.get("userid")
            password = form.get("password")
            totp_code = form.get("totp")
            auth_token, error_message = auth_function(userid, password, totp_code)

    elif broker == "nubra":
        if request.method == "GET":
            return RedirectResponse(url="/broker/nubra/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            totp_code = form.get("totp")
            if not totp_code:
                return JSONResponse({"status": "error", "message": "TOTP code is required."}, status_code=400)
            auth_token, feed_token, error_message = auth_function(totp_code)

    elif broker == "samco":
        if request.method == "GET":
            return RedirectResponse(url="/broker/samco/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            yob = form.get("yob")
            auth_token, error_message = auth_function(yob)

    elif broker == "motilal":
        if request.method == "GET":
            return RedirectResponse(url="/broker/motilal/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            userid = form.get("userid")
            password = form.get("password")
            totp_code = form.get("totp")
            date_of_birth = form.get("dob")
            auth_token, feed_token, error_message = auth_function(userid, password, totp_code, date_of_birth)

    elif broker == "flattrade":
        code = request.query_params.get("code")
        client = request.query_params.get("client")
        logger.debug(f"Flattrade broker - The code is {code} for client {client}")
        auth_token, error_message = auth_function(code)

    elif broker == "kotak":
        if request.method == "GET":
            return RedirectResponse(url="/broker/kotak/totp", status_code=302)
        elif request.method == "POST":
            form = await request.form()
            mobile_number = form.get("mobile") or form.get("mobilenumber")
            totp = form.get("totp")
            mpin = form.get("mpin")

            if not mobile_number or not totp or not mpin:
                return JSONResponse({"status": "error", "message": "Please provide Mobile Number, TOTP, and MPIN"}, status_code=400)

            logger.info(f"Kotak TOTP authentication initiated for mobile: {mobile_number[:5]}***")
            auth_token, error_message = auth_function(mobile_number, totp, mpin)

    elif broker == "paytm":
        request_token = request.query_params.get("requestToken")
        logger.debug(f"Paytm broker - The request token is {request_token}")
        auth_token, feed_token, error_message = auth_function(request_token)

    elif broker == "pocketful":
        auth_code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")
        error_description = request.query_params.get("error_description")

        if error:
            error_msg = f"OAuth error: {error}. {error_description if error_description else ''}"
            logger.error(error_msg)
            return handle_auth_failure_fastapi(request, error_msg, forward_url="broker.html")

        if not auth_code:
            return handle_auth_failure_fastapi(request, "Authorization code not provided", forward_url="broker.html")

        logger.debug(f"Pocketful broker - Received authorization code: {auth_code}")
        auth_token, feed_token, user_id, error_message = auth_function(auth_code, state)

    elif broker == "definedge":
        return await _handle_definedge_callback(request, session, auth_function)

    else:
        code = request.query_params.get("code") or request.query_params.get("request_token")
        logger.debug(f"Generic broker - The code is {code}")
        auth_token, error_message = auth_function(code)

    # Handle successful authentication
    if auth_token:
        session["broker"] = broker
        logger.info(f"Successfully connected broker: {broker}")

        if broker == "zerodha":
            auth_token = f"{BROKER_API_KEY}:{auth_token}"
        if broker == "dhan":
            auth_token = f"{auth_token}"

        if broker in ["angel", "compositedge", "pocketful", "definedge", "dhan"]:
            if broker == "compositedge" and "user" not in session:
                from database.user_db import find_user_by_username
                admin_user = find_user_by_username()
                if admin_user:
                    username = admin_user.username
                    session["user"] = username
                    logger.info(f"Compositedge callback: Set session user to {username}")
                else:
                    logger.error("No admin user found in database for Compositedge callback")
                    return handle_auth_failure_fastapi(request, "No user account found. Please login first.", forward_url="broker.html")

            return handle_auth_success_fastapi(request, auth_token, session["user"], broker, feed_token=feed_token, user_id=user_id)
        elif broker == "paytm":
            return handle_auth_success_fastapi(request, auth_token, session["user"], broker, feed_token=feed_token)
        else:
            return handle_auth_success_fastapi(request, auth_token, session["user"], broker, feed_token=feed_token)
    else:
        return handle_auth_failure_fastapi(request, error_message, forward_url=forward_url)



async def _handle_dhan_callback(request: Request, session: dict, auth_function):
    """Handle Dhan broker callback."""
    auth_token = None
    error_message = None
    forward_url = "broker.html"

    if request.method == "GET":
        logger.info(f"Dhan callback - GET parameters: {dict(request.query_params)}")

        token_id = (
            request.query_params.get("tokenId")
            or request.query_params.get("token_id")
            or request.query_params.get("token")
        )

        if token_id:
            logger.debug(f"Dhan broker - Received tokenId: {token_id}")
            auth_result = auth_function(token_id)

            if len(auth_result) == 3:
                auth_token, user_id, error_message = auth_result
            else:
                auth_token, error_message = auth_result
                user_id = None

            if auth_token:
                from broker.dhan.api.funds import test_auth_token
                is_valid, validation_error = test_auth_token(auth_token)

                if not is_valid:
                    logger.error(f"Dhan authentication validation failed: {validation_error}")
                    return handle_auth_failure_fastapi(request, f"Authentication validation failed: {validation_error}", forward_url="broker.html")

                logger.info("Dhan authentication validation successful")
                session["broker"] = "dhan"
                return handle_auth_success_fastapi(request, auth_token, session["user"], "dhan", user_id=user_id)
            else:
                return handle_auth_failure_fastapi(request, error_message or "Authentication failed", forward_url="broker.html")
        else:
            return RedirectResponse(url="/dhan/initiate-oauth", status_code=302)

    elif request.method == "POST":
        form = await request.form()
        access_token = form.get("access_token")

        if access_token:
            logger.info("Processing direct access token for Dhan")
            auth_token, error_message = auth_function(access_token)

            if auth_token:
                from broker.dhan.api.funds import test_auth_token
                is_valid, validation_error = test_auth_token(auth_token)

                if is_valid:
                    logger.info("Dhan direct token authentication successful")
                    session["broker"] = "dhan"
                    return handle_auth_success_fastapi(request, auth_token, session["user"], "dhan")
                else:
                    logger.error(f"Dhan direct token validation failed: {validation_error}")
                    return JSONResponse({"status": "error", "message": f"Token validation failed: {validation_error}"}, status_code=401)
            else:
                return JSONResponse({"status": "error", "message": error_message or "Invalid access token"}, status_code=401)
        else:
            return JSONResponse({"status": "error", "message": "Please provide either Client ID for OAuth or Access Token for direct login"}, status_code=400)


async def _handle_definedge_callback(request: Request, session: dict, auth_function):
    """Handle Definedge broker callback."""
    if request.method == "GET":
        api_token = get_broker_api_key()
        api_secret = get_broker_api_secret()

        from broker.definedge.api.auth_api import login_step1

        try:
            step1_response = login_step1(api_token, api_secret)
            if step1_response and "otp_token" in step1_response:
                session["definedge_otp_token"] = step1_response["otp_token"]
                otp_message = step1_response.get("message", "OTP has been sent successfully")
                logger.info(f"Definedge OTP triggered: {otp_message}")
                return RedirectResponse(url="/broker/definedge/totp", status_code=302)
            else:
                error_msg = "Failed to send OTP. Please check your API credentials."
                logger.error(f"Definedge OTP generation failed: {step1_response}")
                return JSONResponse({"status": "error", "message": error_msg}, status_code=500)
        except Exception as e:
            error_msg = f"Error sending OTP: {str(e)}"
            logger.error(f"Definedge OTP generation error: {e}")
            return JSONResponse({"status": "error", "message": error_msg}, status_code=500)

    elif request.method == "POST":
        form = await request.form()
        action = form.get("action")

        if action == "resend":
            api_token = get_broker_api_key()
            api_secret = get_broker_api_secret()

            from broker.definedge.api.auth_api import login_step1

            try:
                step1_response = login_step1(api_token, api_secret)
                if step1_response and "otp_token" in step1_response:
                    session["definedge_otp_token"] = step1_response["otp_token"]
                    logger.info("Definedge OTP resent successfully")
                    return JSONResponse({"status": "success", "message": "OTP has been resent successfully"})
                else:
                    return JSONResponse({"status": "error", "message": "Failed to resend OTP"})
            except Exception as e:
                logger.error(f"Definedge OTP resend error: {e}")
                return JSONResponse({"status": "error", "message": str(e)})
        else:
            otp_code = form.get("otp")
            otp_token = session.get("definedge_otp_token")

            if not otp_token:
                return JSONResponse({"status": "error", "message": "Session expired. Please refresh the page to get a new OTP."}, status_code=401)

            api_secret = get_broker_api_secret()

            from broker.definedge.api.auth_api import authenticate_broker

            try:
                auth_token, feed_token, user_id, error_message = authenticate_broker(otp_token, otp_code, api_secret)

                if auth_token:
                    session.pop("definedge_otp_token", None)
                    session["broker"] = "definedge"
                    return handle_auth_success_fastapi(request, auth_token, session["user"], "definedge", feed_token=feed_token, user_id=user_id)
                else:
                    return handle_auth_failure_fastapi(request, error_message, forward_url="broker.html")

            except Exception as e:
                logger.error(f"Definedge OTP verification error: {e}")
                return handle_auth_failure_fastapi(request, str(e), forward_url="broker.html")


@brlogin_router.api_route("/dhan/initiate-oauth", methods=["GET", "POST"])
@limiter.limit(LOGIN_RATE_LIMIT_MIN)
@limiter.limit(LOGIN_RATE_LIMIT_HOUR)
async def dhan_initiate_oauth(request: Request):
    """Handle Dhan OAuth initiation."""
    session = request.session

    if "user" not in session:
        return RedirectResponse(url="/auth/login", status_code=302)

    BROKER_API_KEY = os.getenv("BROKER_API_KEY")
    client_id = None

    if ":::" in BROKER_API_KEY:
        client_id, _ = BROKER_API_KEY.split(":::")

    if not client_id:
        error_message = "Client ID not found in BROKER_API_KEY. Please configure BROKER_API_KEY as 'client_id:::api_key' in .env"
        logger.error(error_message)
        return handle_auth_failure_fastapi(request, error_message, forward_url="broker.html")

    logger.info(f"Initiating Dhan OAuth flow with client ID from .env: {client_id}")

    from broker.dhan.api.auth_api import generate_consent, get_login_url

    consent_app_id, error = generate_consent(client_id)

    if consent_app_id:
        session["consent_app_id"] = consent_app_id
        login_url = get_login_url(consent_app_id)

        if login_url:
            logger.info(f"Redirecting to Dhan OAuth login URL: {login_url}")
            return HTMLResponse(f'''
            <html>
            <head>
                <title>Redirecting to Dhan...</title>
            </head>
            <body>
                <p>Redirecting to Dhan login page...</p>
                <script>
                    window.location.href = "{login_url}";
                </script>
            </body>
            </html>
            ''')
        else:
            error_message = "Failed to generate login URL"
            logger.error(error_message)
            return handle_auth_failure_fastapi(request, error_message, forward_url="broker.html")
    else:
        error_message = error or "Failed to generate consent. Please check your API credentials and Client ID."
        logger.error(error_message)
        return handle_auth_failure_fastapi(request, error_message, forward_url="broker.html")
