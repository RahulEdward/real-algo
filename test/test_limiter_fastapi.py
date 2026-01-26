# test/test_limiter_fastapi.py
"""
Tests for FastAPI Rate Limiter Configuration

Tests the slowapi limiter configuration to ensure:
1. Limiter is properly initialized with correct settings
2. Rate limit format conversion works correctly
3. All rate limit values are preserved from environment
4. IP extraction handles various proxy headers

Requirements: 7.2
"""

import os
import pytest
from unittest.mock import MagicMock, patch


class TestRateLimitFormatConversion:
    """Test rate limit format conversion from Flask-Limiter to slowapi format."""
    
    def test_convert_per_minute_format(self):
        """Test conversion of 'X per minute' format."""
        from limiter_fastapi import _convert_to_slowapi_format
        
        assert _convert_to_slowapi_format("5 per minute") == "5/minute"
        assert _convert_to_slowapi_format("100 per minute") == "100/minute"
    
    def test_convert_per_second_format(self):
        """Test conversion of 'X per second' format."""
        from limiter_fastapi import _convert_to_slowapi_format
        
        assert _convert_to_slowapi_format("10 per second") == "10/second"
        assert _convert_to_slowapi_format("50 per second") == "50/second"
    
    def test_convert_per_hour_format(self):
        """Test conversion of 'X per hour' format."""
        from limiter_fastapi import _convert_to_slowapi_format
        
        assert _convert_to_slowapi_format("25 per hour") == "25/hour"
        assert _convert_to_slowapi_format("15 per hour") == "15/hour"
    
    def test_already_converted_format(self):
        """Test that already converted format is returned as-is."""
        from limiter_fastapi import _convert_to_slowapi_format
        
        assert _convert_to_slowapi_format("5/minute") == "5/minute"
        assert _convert_to_slowapi_format("10/second") == "10/second"
    
    def test_empty_string(self):
        """Test handling of empty string."""
        from limiter_fastapi import _convert_to_slowapi_format
        
        assert _convert_to_slowapi_format("") == ""
    
    def test_case_insensitive(self):
        """Test case insensitive conversion."""
        from limiter_fastapi import _convert_to_slowapi_format
        
        assert _convert_to_slowapi_format("5 PER MINUTE") == "5/minute"
        assert _convert_to_slowapi_format("10 Per Second") == "10/second"


class TestLimiterConfiguration:
    """Test limiter configuration matches Flask-Limiter settings."""
    
    def test_limiter_exists(self):
        """Test that limiter is properly initialized."""
        from limiter_fastapi import limiter
        
        assert limiter is not None
    
    def test_limiter_has_key_func(self):
        """Test that limiter has a key function configured."""
        from limiter_fastapi import limiter
        
        # The limiter should have a key_func attribute
        assert limiter._key_func is not None
    
    def test_limiter_storage_uri(self):
        """Test that limiter uses memory storage."""
        from limiter_fastapi import limiter
        
        # Check that storage is configured (memory storage)
        assert limiter._storage_uri == "memory://"
    
    def test_limiter_strategy(self):
        """Test that limiter uses moving-window strategy."""
        from limiter_fastapi import limiter
        
        # Check that strategy is moving-window
        assert limiter._strategy == "moving-window"


class TestRateLimitValues:
    """Test that rate limit values are correctly loaded from environment."""
    
    def test_login_rate_limit_min_default(self):
        """Test default login rate limit per minute."""
        from limiter_fastapi import get_login_rate_limit_min
        
        # Clear any existing env var
        with patch.dict(os.environ, {}, clear=True):
            result = get_login_rate_limit_min()
            assert result == "5/minute"
    
    def test_login_rate_limit_hour_default(self):
        """Test default login rate limit per hour."""
        from limiter_fastapi import get_login_rate_limit_hour
        
        with patch.dict(os.environ, {}, clear=True):
            result = get_login_rate_limit_hour()
            assert result == "25/hour"
    
    def test_reset_rate_limit_default(self):
        """Test default password reset rate limit."""
        from limiter_fastapi import get_reset_rate_limit
        
        with patch.dict(os.environ, {}, clear=True):
            result = get_reset_rate_limit()
            assert result == "15/hour"
    
    def test_api_rate_limit_default(self):
        """Test default API rate limit."""
        from limiter_fastapi import get_api_rate_limit
        
        with patch.dict(os.environ, {}, clear=True):
            result = get_api_rate_limit()
            assert result == "50/second"
    
    def test_order_rate_limit_default(self):
        """Test default order rate limit."""
        from limiter_fastapi import get_order_rate_limit
        
        with patch.dict(os.environ, {}, clear=True):
            result = get_order_rate_limit()
            assert result == "10/second"
    
    def test_smart_order_rate_limit_default(self):
        """Test default smart order rate limit."""
        from limiter_fastapi import get_smart_order_rate_limit
        
        with patch.dict(os.environ, {}, clear=True):
            result = get_smart_order_rate_limit()
            assert result == "2/second"
    
    def test_webhook_rate_limit_default(self):
        """Test default webhook rate limit."""
        from limiter_fastapi import get_webhook_rate_limit
        
        with patch.dict(os.environ, {}, clear=True):
            result = get_webhook_rate_limit()
            assert result == "100/minute"
    
    def test_strategy_rate_limit_default(self):
        """Test default strategy rate limit."""
        from limiter_fastapi import get_strategy_rate_limit
        
        with patch.dict(os.environ, {}, clear=True):
            result = get_strategy_rate_limit()
            assert result == "200/minute"
    
    def test_custom_env_value(self):
        """Test that custom environment values are respected."""
        from limiter_fastapi import get_api_rate_limit
        
        with patch.dict(os.environ, {"API_RATE_LIMIT": "100 per second"}):
            result = get_api_rate_limit()
            assert result == "100/second"


class TestIPExtraction:
    """Test IP extraction from various proxy headers."""
    
    def _create_mock_request(self, headers: dict = None, client_host: str = "127.0.0.1"):
        """Create a mock FastAPI Request object."""
        request = MagicMock()
        request.headers = headers or {}
        request.client = MagicMock()
        request.client.host = client_host
        return request
    
    def test_cloudflare_ip(self):
        """Test extraction of Cloudflare CF-Connecting-IP header."""
        from limiter_fastapi import get_real_ip
        
        request = self._create_mock_request(
            headers={"CF-Connecting-IP": "203.0.113.50"},
            client_host="10.0.0.1"
        )
        
        assert get_real_ip(request) == "203.0.113.50"
    
    def test_cloudflare_enterprise_ip(self):
        """Test extraction of Cloudflare Enterprise True-Client-IP header."""
        from limiter_fastapi import get_real_ip
        
        request = self._create_mock_request(
            headers={"True-Client-IP": "203.0.113.51"},
            client_host="10.0.0.1"
        )
        
        assert get_real_ip(request) == "203.0.113.51"
    
    def test_x_real_ip(self):
        """Test extraction of X-Real-IP header."""
        from limiter_fastapi import get_real_ip
        
        request = self._create_mock_request(
            headers={"X-Real-IP": "203.0.113.52"},
            client_host="10.0.0.1"
        )
        
        assert get_real_ip(request) == "203.0.113.52"
    
    def test_x_forwarded_for_single(self):
        """Test extraction of single IP from X-Forwarded-For header."""
        from limiter_fastapi import get_real_ip
        
        request = self._create_mock_request(
            headers={"X-Forwarded-For": "203.0.113.53"},
            client_host="10.0.0.1"
        )
        
        assert get_real_ip(request) == "203.0.113.53"
    
    def test_x_forwarded_for_multiple(self):
        """Test extraction of first IP from X-Forwarded-For with multiple IPs."""
        from limiter_fastapi import get_real_ip
        
        request = self._create_mock_request(
            headers={"X-Forwarded-For": "203.0.113.54, 10.0.0.2, 10.0.0.3"},
            client_host="10.0.0.1"
        )
        
        assert get_real_ip(request) == "203.0.113.54"
    
    def test_x_client_ip(self):
        """Test extraction of X-Client-IP header."""
        from limiter_fastapi import get_real_ip
        
        request = self._create_mock_request(
            headers={"X-Client-IP": "203.0.113.55"},
            client_host="10.0.0.1"
        )
        
        assert get_real_ip(request) == "203.0.113.55"
    
    def test_header_priority(self):
        """Test that CF-Connecting-IP takes priority over other headers."""
        from limiter_fastapi import get_real_ip
        
        request = self._create_mock_request(
            headers={
                "CF-Connecting-IP": "203.0.113.50",
                "X-Real-IP": "203.0.113.52",
                "X-Forwarded-For": "203.0.113.53",
            },
            client_host="10.0.0.1"
        )
        
        assert get_real_ip(request) == "203.0.113.50"


class TestRateLimitConstants:
    """Test that rate limit constants are properly exported."""
    
    def test_login_rate_limit_min_constant(self):
        """Test LOGIN_RATE_LIMIT_MIN constant."""
        from limiter_fastapi import LOGIN_RATE_LIMIT_MIN
        
        # Should be in slowapi format
        assert "/" in LOGIN_RATE_LIMIT_MIN
        assert "minute" in LOGIN_RATE_LIMIT_MIN
    
    def test_login_rate_limit_hour_constant(self):
        """Test LOGIN_RATE_LIMIT_HOUR constant."""
        from limiter_fastapi import LOGIN_RATE_LIMIT_HOUR
        
        assert "/" in LOGIN_RATE_LIMIT_HOUR
        assert "hour" in LOGIN_RATE_LIMIT_HOUR
    
    def test_reset_rate_limit_constant(self):
        """Test RESET_RATE_LIMIT constant."""
        from limiter_fastapi import RESET_RATE_LIMIT
        
        assert "/" in RESET_RATE_LIMIT
        assert "hour" in RESET_RATE_LIMIT
    
    def test_api_rate_limit_constant(self):
        """Test API_RATE_LIMIT constant."""
        from limiter_fastapi import API_RATE_LIMIT
        
        assert "/" in API_RATE_LIMIT
        assert "second" in API_RATE_LIMIT
    
    def test_order_rate_limit_constant(self):
        """Test ORDER_RATE_LIMIT constant."""
        from limiter_fastapi import ORDER_RATE_LIMIT
        
        assert "/" in ORDER_RATE_LIMIT
        assert "second" in ORDER_RATE_LIMIT
    
    def test_smart_order_rate_limit_constant(self):
        """Test SMART_ORDER_RATE_LIMIT constant."""
        from limiter_fastapi import SMART_ORDER_RATE_LIMIT
        
        assert "/" in SMART_ORDER_RATE_LIMIT
        assert "second" in SMART_ORDER_RATE_LIMIT
    
    def test_webhook_rate_limit_constant(self):
        """Test WEBHOOK_RATE_LIMIT constant."""
        from limiter_fastapi import WEBHOOK_RATE_LIMIT
        
        assert "/" in WEBHOOK_RATE_LIMIT
        assert "minute" in WEBHOOK_RATE_LIMIT
    
    def test_strategy_rate_limit_constant(self):
        """Test STRATEGY_RATE_LIMIT constant."""
        from limiter_fastapi import STRATEGY_RATE_LIMIT
        
        assert "/" in STRATEGY_RATE_LIMIT
        assert "minute" in STRATEGY_RATE_LIMIT
