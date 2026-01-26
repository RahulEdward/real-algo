#!/usr/bin/env python3
"""
Unit Tests for FastAPI CORS Configuration

This module tests the CORS configuration for FastAPI CORSMiddleware to ensure:
- CORS configuration matches Flask-CORS behavior exactly
- Environment variables are read correctly
- Default values are applied when env vars are not set
- CORS middleware is only added when enabled

Requirements: 7.1
"""

import os
import sys

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from cors_fastapi import get_fastapi_cors_config, is_cors_enabled


class TestCORSConfiguration:
    """Test suite for CORS configuration functions."""
    
    def test_cors_disabled_by_default(self, monkeypatch):
        """CORS should be disabled by default when CORS_ENABLED is not set."""
        monkeypatch.delenv("CORS_ENABLED", raising=False)
        assert is_cors_enabled() is False
    
    def test_cors_disabled_when_false(self, monkeypatch):
        """CORS should be disabled when CORS_ENABLED is FALSE."""
        monkeypatch.setenv("CORS_ENABLED", "FALSE")
        assert is_cors_enabled() is False
    
    def test_cors_enabled_when_true(self, monkeypatch):
        """CORS should be enabled when CORS_ENABLED is TRUE."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        assert is_cors_enabled() is True
    
    def test_cors_enabled_case_insensitive(self, monkeypatch):
        """CORS_ENABLED should be case-insensitive."""
        monkeypatch.setenv("CORS_ENABLED", "true")
        assert is_cors_enabled() is True
        
        monkeypatch.setenv("CORS_ENABLED", "True")
        assert is_cors_enabled() is True
    
    def test_get_config_returns_empty_when_disabled(self, monkeypatch):
        """get_fastapi_cors_config should return empty dict when CORS is disabled."""
        monkeypatch.setenv("CORS_ENABLED", "FALSE")
        config = get_fastapi_cors_config()
        assert config == {}
    
    def test_get_config_returns_empty_when_not_set(self, monkeypatch):
        """get_fastapi_cors_config should return empty dict when CORS_ENABLED is not set."""
        monkeypatch.delenv("CORS_ENABLED", raising=False)
        config = get_fastapi_cors_config()
        assert config == {}


class TestCORSAllowedOrigins:
    """Test suite for CORS allowed origins configuration."""
    
    def test_allowed_origins_from_env(self, monkeypatch):
        """Allowed origins should be read from CORS_ALLOWED_ORIGINS."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,https://example.com")
        
        config = get_fastapi_cors_config()
        assert config["allow_origins"] == ["http://localhost:3000", "https://example.com"]
    
    def test_allowed_origins_strips_whitespace(self, monkeypatch):
        """Allowed origins should strip whitespace from values."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " http://localhost:3000 , https://example.com ")
        
        config = get_fastapi_cors_config()
        assert config["allow_origins"] == ["http://localhost:3000", "https://example.com"]
    
    def test_allowed_origins_empty_when_not_set(self, monkeypatch):
        """Allowed origins should be empty list when not set."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        
        config = get_fastapi_cors_config()
        assert config["allow_origins"] == []
    
    def test_allowed_origins_filters_empty_strings(self, monkeypatch):
        """Allowed origins should filter out empty strings."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,,https://example.com,")
        
        config = get_fastapi_cors_config()
        assert config["allow_origins"] == ["http://localhost:3000", "https://example.com"]


class TestCORSAllowedMethods:
    """Test suite for CORS allowed methods configuration."""
    
    def test_allowed_methods_from_env(self, monkeypatch):
        """Allowed methods should be read from CORS_ALLOWED_METHODS."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_METHODS", "GET,POST,PUT,DELETE")
        
        config = get_fastapi_cors_config()
        assert config["allow_methods"] == ["GET", "POST", "PUT", "DELETE"]
    
    def test_allowed_methods_default(self, monkeypatch):
        """Allowed methods should default to GET,POST when not set."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.delenv("CORS_ALLOWED_METHODS", raising=False)
        
        config = get_fastapi_cors_config()
        assert config["allow_methods"] == ["GET", "POST"]
    
    def test_allowed_methods_strips_whitespace(self, monkeypatch):
        """Allowed methods should strip whitespace from values."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_METHODS", " GET , POST ")
        
        config = get_fastapi_cors_config()
        assert config["allow_methods"] == ["GET", "POST"]


class TestCORSAllowedHeaders:
    """Test suite for CORS allowed headers configuration."""
    
    def test_allowed_headers_from_env(self, monkeypatch):
        """Allowed headers should be read from CORS_ALLOWED_HEADERS."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_HEADERS", "Content-Type,Authorization,X-Custom-Header")
        
        config = get_fastapi_cors_config()
        assert config["allow_headers"] == ["Content-Type", "Authorization", "X-Custom-Header"]
    
    def test_allowed_headers_default_wildcard(self, monkeypatch):
        """Allowed headers should default to wildcard when not set."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.delenv("CORS_ALLOWED_HEADERS", raising=False)
        
        config = get_fastapi_cors_config()
        assert config["allow_headers"] == ["*"]
    
    def test_allowed_headers_strips_whitespace(self, monkeypatch):
        """Allowed headers should strip whitespace from values."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_HEADERS", " Content-Type , Authorization ")
        
        config = get_fastapi_cors_config()
        assert config["allow_headers"] == ["Content-Type", "Authorization"]


class TestCORSExposedHeaders:
    """Test suite for CORS exposed headers configuration."""
    
    def test_exposed_headers_from_env(self, monkeypatch):
        """Exposed headers should be read from CORS_EXPOSED_HEADERS."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_EXPOSED_HEADERS", "X-Custom-Header,X-Request-Id")
        
        config = get_fastapi_cors_config()
        assert config["expose_headers"] == ["X-Custom-Header", "X-Request-Id"]
    
    def test_exposed_headers_not_in_config_when_not_set(self, monkeypatch):
        """Exposed headers should not be in config when not set."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.delenv("CORS_EXPOSED_HEADERS", raising=False)
        
        config = get_fastapi_cors_config()
        assert "expose_headers" not in config
    
    def test_exposed_headers_strips_whitespace(self, monkeypatch):
        """Exposed headers should strip whitespace from values."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_EXPOSED_HEADERS", " X-Custom-Header , X-Request-Id ")
        
        config = get_fastapi_cors_config()
        assert config["expose_headers"] == ["X-Custom-Header", "X-Request-Id"]


class TestCORSCredentials:
    """Test suite for CORS credentials configuration."""
    
    def test_credentials_enabled_when_true(self, monkeypatch):
        """Credentials should be enabled when CORS_ALLOW_CREDENTIALS is TRUE."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "TRUE")
        
        config = get_fastapi_cors_config()
        assert config["allow_credentials"] is True
    
    def test_credentials_disabled_by_default(self, monkeypatch):
        """Credentials should be disabled by default."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.delenv("CORS_ALLOW_CREDENTIALS", raising=False)
        
        config = get_fastapi_cors_config()
        assert config["allow_credentials"] is False
    
    def test_credentials_disabled_when_false(self, monkeypatch):
        """Credentials should be disabled when CORS_ALLOW_CREDENTIALS is FALSE."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "FALSE")
        
        config = get_fastapi_cors_config()
        assert config["allow_credentials"] is False
    
    def test_credentials_case_insensitive(self, monkeypatch):
        """CORS_ALLOW_CREDENTIALS should be case-insensitive."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
        
        config = get_fastapi_cors_config()
        assert config["allow_credentials"] is True


class TestCORSMaxAge:
    """Test suite for CORS max age configuration."""
    
    def test_max_age_from_env(self, monkeypatch):
        """Max age should be read from CORS_MAX_AGE."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_MAX_AGE", "3600")
        
        config = get_fastapi_cors_config()
        assert config["max_age"] == 3600
    
    def test_max_age_default(self, monkeypatch):
        """Max age should default to 600 when not set."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.delenv("CORS_MAX_AGE", raising=False)
        
        config = get_fastapi_cors_config()
        assert config["max_age"] == 600
    
    def test_max_age_invalid_uses_default(self, monkeypatch):
        """Max age should use default when value is not a valid integer."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_MAX_AGE", "invalid")
        
        config = get_fastapi_cors_config()
        assert config["max_age"] == 600
    
    def test_max_age_negative_uses_default(self, monkeypatch):
        """Max age should use default when value is negative (not a digit)."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_MAX_AGE", "-100")
        
        config = get_fastapi_cors_config()
        assert config["max_age"] == 600


class TestCORSMiddlewareIntegration:
    """Test suite for CORS middleware integration with FastAPI."""
    
    def test_cors_headers_added_when_enabled(self, monkeypatch):
        """CORS headers should be added to responses when CORS is enabled."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
        monkeypatch.setenv("CORS_ALLOWED_METHODS", "GET,POST")
        
        app = FastAPI()
        cors_config = get_fastapi_cors_config()
        app.add_middleware(CORSMiddleware, **cors_config)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        
        # Make a preflight request
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    
    def test_cors_credentials_header_when_enabled(self, monkeypatch):
        """Access-Control-Allow-Credentials header should be set when credentials are enabled."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
        monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "TRUE")
        
        app = FastAPI()
        cors_config = get_fastapi_cors_config()
        app.add_middleware(CORSMiddleware, **cors_config)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        
        response = client.get(
            "/test",
            headers={"Origin": "http://localhost:3000"}
        )
        
        assert response.headers.get("access-control-allow-credentials") == "true"
    
    def test_cors_not_applied_for_non_cors_request(self, monkeypatch):
        """CORS headers should not be added for non-CORS requests (no Origin header)."""
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
        
        app = FastAPI()
        cors_config = get_fastapi_cors_config()
        app.add_middleware(CORSMiddleware, **cors_config)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        
        # Request without Origin header
        response = client.get("/test")
        
        assert "access-control-allow-origin" not in response.headers


class TestFlaskCORSCompatibility:
    """Test suite to verify Flask-CORS behavior compatibility."""
    
    def test_config_mapping_flask_to_fastapi(self, monkeypatch):
        """
        Verify that Flask-CORS config keys map correctly to FastAPI CORSMiddleware.
        
        Flask-CORS uses:
        - origins -> allow_origins
        - methods -> allow_methods
        - allow_headers -> allow_headers
        - expose_headers -> expose_headers
        - supports_credentials -> allow_credentials
        - max_age -> max_age
        """
        monkeypatch.setenv("CORS_ENABLED", "TRUE")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
        monkeypatch.setenv("CORS_ALLOWED_METHODS", "GET,POST,PUT")
        monkeypatch.setenv("CORS_ALLOWED_HEADERS", "Content-Type,Authorization")
        monkeypatch.setenv("CORS_EXPOSED_HEADERS", "X-Custom-Header")
        monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "TRUE")
        monkeypatch.setenv("CORS_MAX_AGE", "3600")
        
        config = get_fastapi_cors_config()
        
        # Verify all FastAPI CORSMiddleware keys are present
        assert "allow_origins" in config
        assert "allow_methods" in config
        assert "allow_headers" in config
        assert "expose_headers" in config
        assert "allow_credentials" in config
        assert "max_age" in config
        
        # Verify values
        assert config["allow_origins"] == ["http://localhost:3000"]
        assert config["allow_methods"] == ["GET", "POST", "PUT"]
        assert config["allow_headers"] == ["Content-Type", "Authorization"]
        assert config["expose_headers"] == ["X-Custom-Header"]
        assert config["allow_credentials"] is True
        assert config["max_age"] == 3600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
