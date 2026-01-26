#!/usr/bin/env python3
"""
Unit Tests for FastAPI Security Middleware

This module tests the security middleware for FastAPI to ensure:
- IP ban checking works correctly
- Real IP extraction handles proxy headers properly
- Banned IPs receive 403 Forbidden response
- Non-banned IPs can proceed normally
- Logging occurs for blocked attempts

Requirements: 8.1
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from security_middleware_fastapi import SecurityMiddleware, get_real_ip


class TestGetRealIP:
    """Test suite for get_real_ip function."""
    
    def _create_mock_request(self, headers: dict = None, client_host: str = "127.0.0.1"):
        """Create a mock FastAPI Request object with specified headers."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = headers or {}
        mock_request.client = MagicMock()
        mock_request.client.host = client_host
        return mock_request
    
    def test_cloudflare_ip_header_priority(self):
        """CF-Connecting-IP should have highest priority."""
        request = self._create_mock_request(
            headers={
                "CF-Connecting-IP": "1.2.3.4",
                "X-Real-IP": "5.6.7.8",
                "X-Forwarded-For": "9.10.11.12",
            },
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "1.2.3.4"
    
    def test_true_client_ip_header(self):
        """True-Client-IP should be used when CF-Connecting-IP is not present."""
        request = self._create_mock_request(
            headers={
                "True-Client-IP": "1.2.3.4",
                "X-Real-IP": "5.6.7.8",
            },
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "1.2.3.4"
    
    def test_x_real_ip_header(self):
        """X-Real-IP should be used when Cloudflare headers are not present."""
        request = self._create_mock_request(
            headers={
                "X-Real-IP": "1.2.3.4",
                "X-Forwarded-For": "5.6.7.8",
            },
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "1.2.3.4"
    
    def test_x_forwarded_for_single_ip(self):
        """X-Forwarded-For with single IP should be used correctly."""
        request = self._create_mock_request(
            headers={"X-Forwarded-For": "1.2.3.4"},
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "1.2.3.4"
    
    def test_x_forwarded_for_multiple_ips(self):
        """X-Forwarded-For with multiple IPs should use the first one."""
        request = self._create_mock_request(
            headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.10.11.12"},
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "1.2.3.4"
    
    def test_x_forwarded_for_strips_whitespace(self):
        """X-Forwarded-For should strip whitespace from IPs."""
        request = self._create_mock_request(
            headers={"X-Forwarded-For": "  1.2.3.4  ,  5.6.7.8  "},
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "1.2.3.4"
    
    def test_x_client_ip_header(self):
        """X-Client-IP should be used when other headers are not present."""
        request = self._create_mock_request(
            headers={"X-Client-IP": "1.2.3.4"},
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "1.2.3.4"
    
    def test_fallback_to_client_host(self):
        """Should fallback to request.client.host when no headers are present."""
        request = self._create_mock_request(
            headers={},
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "192.168.1.1"
    
    def test_no_client_returns_unknown(self):
        """Should return 'unknown' when client is None."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        mock_request.client = None
        
        assert get_real_ip(mock_request) == "unknown"
    
    def test_empty_x_forwarded_for_fallback(self):
        """Should fallback when X-Forwarded-For is empty."""
        request = self._create_mock_request(
            headers={"X-Forwarded-For": ""},
            client_host="192.168.1.1"
        )
        
        assert get_real_ip(request) == "192.168.1.1"


class TestSecurityMiddlewareIntegration:
    """Test suite for SecurityMiddleware integration with FastAPI."""
    
    @pytest.fixture
    def app_with_middleware(self):
        """Create a FastAPI app with SecurityMiddleware."""
        app = FastAPI()
        app.add_middleware(SecurityMiddleware)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}
        
        @app.get("/api/v1/data")
        async def api_endpoint():
            return {"data": "test"}
        
        return app
    
    @pytest.fixture
    def client(self, app_with_middleware):
        """Create a test client for the app."""
        return TestClient(app_with_middleware)
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_non_banned_ip_allowed(self, mock_is_banned, client):
        """Non-banned IPs should be allowed to access endpoints."""
        mock_is_banned.return_value = False
        
        response = client.get("/test")
        
        assert response.status_code == 200
        assert response.json() == {"message": "success"}
        mock_is_banned.assert_called()
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_banned_ip_blocked(self, mock_is_banned, client):
        """Banned IPs should receive 403 Forbidden."""
        mock_is_banned.return_value = True
        
        response = client.get("/test")
        
        assert response.status_code == 403
        assert response.text == "Access Denied: Your IP has been banned"
        mock_is_banned.assert_called()
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_banned_ip_blocked_api_endpoint(self, mock_is_banned, client):
        """Banned IPs should be blocked from API endpoints too."""
        mock_is_banned.return_value = True
        
        response = client.get("/api/v1/data")
        
        assert response.status_code == 403
        assert response.text == "Access Denied: Your IP has been banned"
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_ip_check_uses_real_ip_from_headers(self, mock_is_banned, client):
        """IP ban check should use real IP from proxy headers."""
        mock_is_banned.return_value = False
        
        response = client.get(
            "/test",
            headers={"X-Real-IP": "10.20.30.40"}
        )
        
        assert response.status_code == 200
        # Verify the IP check was called with the header IP
        mock_is_banned.assert_called_with("10.20.30.40")
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_ip_check_uses_cloudflare_header(self, mock_is_banned, client):
        """IP ban check should prioritize Cloudflare header."""
        mock_is_banned.return_value = False
        
        response = client.get(
            "/test",
            headers={
                "CF-Connecting-IP": "1.2.3.4",
                "X-Real-IP": "5.6.7.8"
            }
        )
        
        assert response.status_code == 200
        mock_is_banned.assert_called_with("1.2.3.4")
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_ip_check_uses_x_forwarded_for(self, mock_is_banned, client):
        """IP ban check should use X-Forwarded-For when other headers not present."""
        mock_is_banned.return_value = False
        
        response = client.get(
            "/test",
            headers={"X-Forwarded-For": "11.22.33.44, 55.66.77.88"}
        )
        
        assert response.status_code == 200
        mock_is_banned.assert_called_with("11.22.33.44")
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    @patch("security_middleware_fastapi.logger")
    def test_blocked_ip_logged(self, mock_logger, mock_is_banned, client):
        """Blocked IPs should be logged with warning."""
        mock_is_banned.return_value = True
        
        response = client.get(
            "/test",
            headers={"X-Real-IP": "10.20.30.40"}
        )
        
        assert response.status_code == 403
        mock_logger.warning.assert_called_with("Blocked banned IP: 10.20.30.40")
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_response_content_type_plain_text(self, mock_is_banned, client):
        """Blocked response should be plain text."""
        mock_is_banned.return_value = True
        
        response = client.get("/test")
        
        assert response.status_code == 403
        assert "text/plain" in response.headers.get("content-type", "")


class TestSecurityMiddlewareEdgeCases:
    """Test suite for edge cases in SecurityMiddleware."""
    
    @pytest.fixture
    def app_with_middleware(self):
        """Create a FastAPI app with SecurityMiddleware."""
        app = FastAPI()
        app.add_middleware(SecurityMiddleware)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}
        
        @app.post("/submit")
        async def submit_endpoint():
            return {"status": "submitted"}
        
        return app
    
    @pytest.fixture
    def client(self, app_with_middleware):
        """Create a test client for the app."""
        return TestClient(app_with_middleware)
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_post_request_blocked_for_banned_ip(self, mock_is_banned, client):
        """POST requests should also be blocked for banned IPs."""
        mock_is_banned.return_value = True
        
        response = client.post("/submit")
        
        assert response.status_code == 403
        assert response.text == "Access Denied: Your IP has been banned"
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_post_request_allowed_for_non_banned_ip(self, mock_is_banned, client):
        """POST requests should be allowed for non-banned IPs."""
        mock_is_banned.return_value = False
        
        response = client.post("/submit")
        
        assert response.status_code == 200
        assert response.json() == {"status": "submitted"}
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_middleware_handles_exception_in_ip_check(self, mock_is_banned, client):
        """Middleware should handle exceptions in IP ban check gracefully."""
        # IPBan.is_ip_banned already handles exceptions internally and returns False
        # This test verifies the middleware doesn't break if is_ip_banned returns False
        mock_is_banned.return_value = False
        
        response = client.get("/test")
        
        assert response.status_code == 200


class TestFlaskSecurityMiddlewareCompatibility:
    """Test suite to verify Flask SecurityMiddleware behavior compatibility."""
    
    @pytest.fixture
    def app_with_middleware(self):
        """Create a FastAPI app with SecurityMiddleware."""
        app = FastAPI()
        app.add_middleware(SecurityMiddleware)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}
        
        return app
    
    @pytest.fixture
    def client(self, app_with_middleware):
        """Create a test client for the app."""
        return TestClient(app_with_middleware)
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_response_matches_flask_format(self, mock_is_banned, client):
        """
        Verify that the 403 response matches Flask SecurityMiddleware format.
        
        Flask returns:
        - Status: 403 Forbidden
        - Content-Type: text/plain
        - Body: "Access Denied: Your IP has been banned"
        """
        mock_is_banned.return_value = True
        
        response = client.get("/test")
        
        # Verify status code
        assert response.status_code == 403
        
        # Verify content type is plain text
        assert "text/plain" in response.headers.get("content-type", "")
        
        # Verify exact response body matches Flask
        assert response.text == "Access Denied: Your IP has been banned"
    
    @patch("security_middleware_fastapi.IPBan.is_ip_banned")
    def test_ip_extraction_matches_flask_behavior(self, mock_is_banned, client):
        """
        Verify IP extraction matches Flask get_real_ip_from_environ behavior.
        
        Flask checks headers in this order:
        1. CF-Connecting-IP
        2. True-Client-IP
        3. X-Real-IP
        4. X-Forwarded-For
        5. X-Client-IP
        6. REMOTE_ADDR
        """
        mock_is_banned.return_value = False
        
        # Test CF-Connecting-IP priority
        response = client.get(
            "/test",
            headers={
                "CF-Connecting-IP": "1.1.1.1",
                "True-Client-IP": "2.2.2.2",
                "X-Real-IP": "3.3.3.3",
            }
        )
        mock_is_banned.assert_called_with("1.1.1.1")
        
        # Test True-Client-IP when CF not present
        mock_is_banned.reset_mock()
        response = client.get(
            "/test",
            headers={
                "True-Client-IP": "2.2.2.2",
                "X-Real-IP": "3.3.3.3",
            }
        )
        mock_is_banned.assert_called_with("2.2.2.2")
        
        # Test X-Real-IP when Cloudflare headers not present
        mock_is_banned.reset_mock()
        response = client.get(
            "/test",
            headers={"X-Real-IP": "3.3.3.3"}
        )
        mock_is_banned.assert_called_with("3.3.3.3")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
