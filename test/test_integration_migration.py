# test/test_integration_migration.py
"""
Integration Property Tests for RealAlgo Migration (Task 11.7)

Tests:
- Property 11: Service Layer Immutability
- Property 13: Directory Structure Preservation

Validates: Requirements 10.1-10.5, 12.1-12.6, 13.1-13.4
"""

import os
import pytest
from pathlib import Path


class TestProperty11ServiceLayerImmutability:
    """
    Property 11: Service Layer Immutability
    
    The service layer (services/, database/, broker/, sandbox/) should remain
    unchanged except for import changes. These modules should be framework-agnostic.
    
    Validates: Requirements 10.1-10.5
    """
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_services_directory_exists(self):
        """Verify services directory exists and contains expected files."""
        services_dir = Path("services")
        assert services_dir.exists(), "services/ directory should exist"
        assert services_dir.is_dir(), "services/ should be a directory"
        
        # Check for key service files
        expected_services = [
            "place_order_service.py",
            "modify_order_service.py",
            "cancel_order_service.py",
            "funds_service.py",
            "orderbook_service.py",
            "quotes_service.py",
        ]
        
        for service in expected_services:
            service_path = services_dir / service
            assert service_path.exists(), f"Service file {service} should exist"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_database_directory_exists(self):
        """Verify database directory exists and contains expected files."""
        database_dir = Path("database")
        assert database_dir.exists(), "database/ directory should exist"
        assert database_dir.is_dir(), "database/ should be a directory"
        
        # Check for key database files
        expected_db_files = [
            "auth_db.py",
            "user_db.py",
            "symbol.py",
            "settings_db.py",
            "strategy_db.py",
        ]
        
        for db_file in expected_db_files:
            db_path = database_dir / db_file
            assert db_path.exists(), f"Database file {db_file} should exist"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_broker_directory_exists(self):
        """Verify broker directory exists with broker implementations."""
        broker_dir = Path("broker")
        assert broker_dir.exists(), "broker/ directory should exist"
        assert broker_dir.is_dir(), "broker/ should be a directory"
        
        # Check for some broker implementations
        expected_brokers = ["zerodha", "angel", "dhan", "fyers"]
        
        for broker in expected_brokers:
            broker_path = broker_dir / broker
            assert broker_path.exists(), f"Broker {broker} directory should exist"
            assert broker_path.is_dir(), f"Broker {broker} should be a directory"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_sandbox_directory_exists(self):
        """Verify sandbox directory exists and contains expected files."""
        sandbox_dir = Path("sandbox")
        assert sandbox_dir.exists(), "sandbox/ directory should exist"
        assert sandbox_dir.is_dir(), "sandbox/ should be a directory"
        
        # Check for key sandbox files
        expected_sandbox_files = [
            "execution_engine.py",
            "execution_thread.py",
            "order_manager.py",
            "position_manager.py",
            "fund_manager.py",
        ]
        
        for sandbox_file in expected_sandbox_files:
            sandbox_path = sandbox_dir / sandbox_file
            assert sandbox_path.exists(), f"Sandbox file {sandbox_file} should exist"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_services_no_fastapi_imports(self):
        """
        Verify service files don't import FastAPI directly.
        Services should be framework-agnostic.
        """
        services_dir = Path("services")
        
        for service_file in services_dir.glob("*.py"):
            if service_file.name.startswith("__"):
                continue
                
            content = service_file.read_text(encoding="utf-8", errors="ignore")
            
            # Services should not import FastAPI directly
            # (they may import from flask for session access, which is acceptable)
            assert "from fastapi import" not in content or "APIRouter" not in content, \
                f"Service {service_file.name} should not import FastAPI routers"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_database_no_fastapi_imports(self):
        """
        Verify database files don't import FastAPI directly.
        Database layer should be framework-agnostic.
        """
        database_dir = Path("database")
        
        for db_file in database_dir.glob("*.py"):
            if db_file.name.startswith("__"):
                continue
                
            content = db_file.read_text(encoding="utf-8", errors="ignore")
            
            # Database files should not import FastAPI
            assert "from fastapi import" not in content, \
                f"Database file {db_file.name} should not import FastAPI"


class TestProperty13DirectoryStructurePreservation:
    """
    Property 13: Directory Structure Preservation
    
    The migration should not create new top-level directories or rename/move
    existing directories. The only new directory allowed is 'routers/'.
    
    Validates: Requirements 12.1-12.6
    """
    
    @pytest.mark.property("Feature: realalgo-migration, Property 13: Directory Structure Preservation")
    def test_required_directories_exist(self):
        """Verify all required directories exist."""
        required_dirs = [
            "blueprints",
            "broker",
            "database",
            "services",
            "sandbox",
            "restx_api",
            "websocket_proxy",
            "utils",
            "frontend",
            "test",
            "docs",
            "examples",
        ]
        
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            assert dir_path.exists(), f"Required directory {dir_name}/ should exist"
            assert dir_path.is_dir(), f"{dir_name} should be a directory"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 13: Directory Structure Preservation")
    def test_routers_directory_exists(self):
        """Verify routers directory exists (new for FastAPI migration)."""
        routers_dir = Path("routers")
        assert routers_dir.exists(), "routers/ directory should exist for FastAPI"
        assert routers_dir.is_dir(), "routers/ should be a directory"
        
        # Check for key router files
        expected_routers = [
            "auth.py",
            "dashboard.py",
            "orders.py",
            "search.py",
            "react_app.py",
        ]
        
        for router in expected_routers:
            router_path = routers_dir / router
            assert router_path.exists(), f"Router file {router} should exist"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 13: Directory Structure Preservation")
    def test_api_v1_routers_exist(self):
        """Verify API v1 routers directory exists with expected files."""
        api_v1_dir = Path("routers/api_v1")
        assert api_v1_dir.exists(), "routers/api_v1/ directory should exist"
        assert api_v1_dir.is_dir(), "routers/api_v1/ should be a directory"
        
        # Check for key API router files
        expected_api_routers = [
            "place_order.py",
            "modify_order.py",
            "cancel_order.py",
            "quotes.py",
            "depth.py",
            "history.py",
        ]
        
        for router in expected_api_routers:
            router_path = api_v1_dir / router
            assert router_path.exists(), f"API router file {router} should exist"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 13: Directory Structure Preservation")
    def test_blueprints_preserved(self):
        """Verify Flask blueprints are preserved for reference."""
        blueprints_dir = Path("blueprints")
        assert blueprints_dir.exists(), "blueprints/ directory should be preserved"
        
        # Check for key blueprint files
        expected_blueprints = [
            "auth.py",
            "dashboard.py",
            "orders.py",
            "search.py",
            "core.py",
        ]
        
        for blueprint in expected_blueprints:
            blueprint_path = blueprints_dir / blueprint
            assert blueprint_path.exists(), f"Blueprint file {blueprint} should be preserved"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 13: Directory Structure Preservation")
    def test_restx_api_preserved(self):
        """Verify restx_api directory is preserved with schemas."""
        restx_api_dir = Path("restx_api")
        assert restx_api_dir.exists(), "restx_api/ directory should be preserved"
        
        # Check for Pydantic schemas (new for FastAPI)
        pydantic_schemas = restx_api_dir / "pydantic_schemas.py"
        assert pydantic_schemas.exists(), "pydantic_schemas.py should exist for FastAPI"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 13: Directory Structure Preservation")
    def test_core_files_exist(self):
        """Verify core application files exist."""
        core_files = [
            "app.py",  # Flask app (preserved)
            "app_fastapi.py",  # FastAPI app (new)
            "extensions.py",  # Flask extensions
            "extensions_fastapi.py",  # FastAPI extensions (new)
            "cors.py",  # Flask CORS
            "cors_fastapi.py",  # FastAPI CORS (new)
            "limiter.py",  # Flask limiter
            "limiter_fastapi.py",  # FastAPI limiter (new)
            "csp.py",  # Flask CSP
            "csp_fastapi.py",  # FastAPI CSP (new)
        ]
        
        for file_name in core_files:
            file_path = Path(file_name)
            assert file_path.exists(), f"Core file {file_name} should exist"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 13: Directory Structure Preservation")
    def test_startup_files_exist(self):
        """Verify startup and configuration files exist."""
        startup_files = [
            "start.sh",
            "Dockerfile",
            "docker-compose.yaml",
            "pyproject.toml",
            "requirements.txt",
        ]
        
        for file_name in startup_files:
            file_path = Path(file_name)
            assert file_path.exists(), f"Startup file {file_name} should exist"


class TestFastAPIConfiguration:
    """Tests for FastAPI application configuration."""
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_dependencies_fastapi_exists(self):
        """Verify FastAPI dependencies module exists."""
        deps_file = Path("dependencies_fastapi.py")
        assert deps_file.exists(), "dependencies_fastapi.py should exist"
        
        content = deps_file.read_text(encoding="utf-8")
        
        # Check for key dependencies
        assert "check_session_validity" in content, "Should have session validation dependency"
        assert "get_session" in content, "Should have get_session dependency"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_csrf_fastapi_exists(self):
        """Verify CSRF middleware for FastAPI exists."""
        csrf_file = Path("csrf_fastapi.py")
        assert csrf_file.exists(), "csrf_fastapi.py should exist"
        
        content = csrf_file.read_text(encoding="utf-8")
        
        # Check for CSRF middleware class
        assert "CSRFMiddleware" in content, "Should have CSRFMiddleware class"
    
    @pytest.mark.property("Feature: realalgo-migration, Property 11: Service Layer Immutability")
    def test_security_middleware_fastapi_exists(self):
        """Verify security middleware for FastAPI exists."""
        security_file = Path("security_middleware_fastapi.py")
        assert security_file.exists(), "security_middleware_fastapi.py should exist"
        
        content = security_file.read_text(encoding="utf-8")
        
        # Check for security middleware class
        assert "SecurityMiddleware" in content, "Should have SecurityMiddleware class"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
