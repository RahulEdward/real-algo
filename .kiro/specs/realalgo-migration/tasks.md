# Implementation Plan: RealAlgo Migration

## Overview

This implementation plan covers the migration from Flask to FastAPI and rebranding from OpenAlgo to RealAlgo. The migration is organized into 6 phases, each independently testable with rollback capability.

## Tasks

- [x] 1. Phase 1: Rebranding (OpenAlgo → RealAlgo)
  - [x] 1.1 Create rebranding utility script
    - Create `scripts/rebrand.py` with find-and-replace logic
    - Support dry-run mode to preview changes
    - Handle case-sensitive and case-insensitive replacements
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.2 Update Python source files
    - Replace "OpenAlgo" with "RealAlgo" in all .py files
    - Replace "openalgo" with "realalgo" in all .py files
    - Update docstrings and comments
    - _Requirements: 1.1, 1.2_

  - [x] 1.3 Update configuration files
    - Update .env and .sample.env files
    - Update docker-compose.yaml
    - Update pyproject.toml
    - Update package.json (root level)
    - _Requirements: 1.3_

  - [x] 1.4 Update documentation files
    - Update README.md, INSTALL.md, CONTRIBUTING.md
    - Update all files in docs/ folder
    - Update CHANGELOG.md
    - _Requirements: 1.4_

  - [x] 1.5 Update database references
    - Rename db/openalgo.db to db/realalgo.db
    - Update database path references in code
    - _Requirements: 1.5_

  - [x] 1.6 Update API documentation
    - Update API title in restx_api/__init__.py
    - Update version utility in utils/version.py
    - Update /auth/app-info endpoint response
    - _Requirements: 1.6, 1.7_

  - [x] 1.7 Update frontend branding
    - Update all "OpenAlgo" text in frontend/src/
    - Update frontend/package.json openalgo dependency
    - Update index.html title and meta tags
    - Identify logo files requiring manual replacement
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 1.8 Update collections and examples
    - Rename collections/openalgo_bruno.json to realalgo_bruno.json
    - Update internal references in collection files
    - Update examples/ folder references
    - _Requirements: 2.5_

  - [x] 1.9 Write property tests for rebranding completeness
    - **Property 1: Rebranding Completeness - Python Files**
    - **Property 2: Rebranding Completeness - Configuration and Documentation**
    - **Property 3: Frontend Rebranding Completeness**
    - **Validates: Requirements 1.1-1.7, 2.1-2.5**

- [x] 2. Checkpoint - Phase 1 Complete
  - Verify Flask app still runs with new branding
  - Run existing test suite
  - Ensure all tests pass, ask the user if questions arise

- [ ] 3. Phase 2: FastAPI Core Application Setup
  - [x] 3.1 Install FastAPI dependencies
    - Add fastapi, uvicorn, python-multipart to requirements.txt
    - Add slowapi for rate limiting
    - Add python-socketio[asgi] for WebSocket
    - Add starlette for middleware
    - _Requirements: 3.1_

  - [x] 3.2 Create FastAPI application skeleton
    - Create app_fastapi.py with FastAPI initialization
    - Implement lifespan context manager for startup/shutdown
    - Configure secret key and database URI from environment
    - _Requirements: 3.1, 3.4_

  - [x] 3.3 Implement session middleware
    - Configure SessionMiddleware with identical cookie settings
    - Implement HTTPONLY, SAMESITE, SECURE settings
    - Handle __Secure- prefix for HTTPS
    - _Requirements: 3.2_

  - [x] 3.4 Implement CSRF middleware
    - Create CSRFMiddleware class
    - Exempt /api/v1/ paths (use API key auth)
    - Implement token generation and validation
    - _Requirements: 3.3_

  - [x] 3.5 Implement error handlers
    - Create exception handlers for 400, 401, 403, 404, 429, 500
    - Match Flask error response formats exactly
    - Implement React app serving for 404
    - _Requirements: 3.5, 3.6_

  - [x] 3.6 Port CORS configuration
    - Create get_cors_config() for FastAPI CORSMiddleware
    - Read configuration from environment variables
    - Match Flask-CORS behavior exactly
    - _Requirements: 7.1_

  - [x] 3.7 Port rate limiter configuration
    - Update limiter.py to use slowapi
    - Preserve all rate limit values
    - Configure memory storage and moving-window strategy
    - _Requirements: 7.2_

  - [x] 3.8 Port security middleware
    - Convert SecurityMiddleware to FastAPI BaseHTTPMiddleware
    - Implement IP ban checking
    - Match Flask security middleware behavior
    - _Requirements: 8.1_

  - [x] 3.9 Port CSP middleware
    - Convert CSP middleware to FastAPI BaseHTTPMiddleware
    - Implement all security headers
    - Match Flask CSP configuration
    - _Requirements: 8.3_

  - [x] 3.10 Write property tests for core configuration
    - **Property 8: Session Cookie Configuration Equivalence**
    - **Property 9: CSRF Token Round-Trip**
    - **Property 14: Middleware Header Equivalence**
    - **Validates: Requirements 3.2, 3.3, 7.1, 7.2, 8.1, 8.3**

- [x] 4. Checkpoint - Phase 2 Complete
  - Verify FastAPI app starts successfully
  - Test basic middleware functionality
  - Ensure all tests pass, ask the user if questions arise

- [x] 5. Phase 3: Blueprint to Router Migration
  - [x] 5.1 Create session dependency
    - Implement get_session() dependency
    - Implement check_session_validity() dependency
    - Port session validation logic from utils/session.py
    - _Requirements: 4.5, 7.3_

  - [x] 5.2 Convert auth blueprint to router
    - Create blueprints/auth.py FastAPI router
    - Port all auth routes (login, logout, password reset, TOTP)
    - Preserve exact URL patterns and response formats
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6_

  - [x] 5.3 Convert dashboard blueprint to router
    - Port dashboard routes
    - Implement session-protected routes
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.4 Convert orders blueprint to router
    - Port orders routes
    - Preserve response formats
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.5 Convert search blueprint to router
    - Port search routes
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.6 Convert apikey blueprint to router
    - Port API key management routes
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.7 Convert remaining web blueprints (batch 1)
    - Port log, platforms, brlogin, core blueprints
    - _Requirements: 4.7_

  - [x] 5.8 Convert remaining web blueprints (batch 2)
    - Port analyzer, settings, chartink, traffic blueprints
    - _Requirements: 4.7_

  - [x] 5.9 Convert remaining web blueprints (batch 3)
    - Port latency, strategy, master_contract_status, pnltracker blueprints
    - _Requirements: 4.7_

  - [x] 5.10 Convert remaining web blueprints (batch 4)
    - Port python_strategy, telegram, security, sandbox blueprints
    - _Requirements: 4.7_

  - [x] 5.11 Convert remaining web blueprints (batch 5)
    - Port playground, logging, admin, historify, flow blueprints
    - _Requirements: 4.7_

  - [x] 5.12 Convert remaining web blueprints (batch 6)
    - Port broker_credentials, system_permissions, tv_json, gc_json blueprints
    - _Requirements: 4.7_

  - [x] 5.13 Convert React app blueprint
    - Port react_app blueprint for serving React frontend
    - Implement static file serving
    - _Requirements: 4.7_

  - [x] 5.14 Register all routers in FastAPI app
    - Import and include all routers
    - Verify URL prefixes match Flask blueprints
    - _Requirements: 4.1, 4.7_

  - [x] 5.15 Write property tests for blueprint migration
    - **Property 4: Blueprint to Router URL Preservation**
    - **Property 15: Authentication Flow Equivalence**
    - **Validates: Requirements 4.1-4.7**

- [x] 6. Checkpoint - Phase 3 Complete
  - Verify all web routes accessible
  - Test authentication flows
  - Ensure all tests pass, ask the user if questions arise

- [x] 7. Phase 4: REST API Migration
  - [x] 7.1 Create Pydantic models for API schemas
    - Create restx_api/pydantic_schemas.py
    - Define request models (PlaceOrderRequest, ModifyOrderRequest, etc.)
    - Define response models (OrderResponse, FundsResponse, etc.)
    - _Requirements: 5.2_

  - [x] 7.2 Create API key authentication dependency
    - Implement verify_api_key dependency
    - Port API key validation logic
    - _Requirements: 5.1_

  - [x] 7.3 Convert place_order endpoint
    - Create FastAPI router for /api/v1/placeorder
    - Use Pydantic models for validation
    - Preserve exact response format
    - _Requirements: 5.1, 5.3, 5.4_

  - [x] 7.4 Convert order management endpoints
    - Port modify_order, cancel_order, cancel_all_order
    - Port orderstatus, orderbook, tradebook
    - _Requirements: 5.1, 5.3, 5.6_

  - [x] 7.5 Convert position and holdings endpoints
    - Port openposition, positionbook, holdings
    - Port close_position
    - _Requirements: 5.1, 5.3, 5.6_

  - [x] 7.6 Convert market data endpoints
    - Port quotes, multiquotes, depth
    - Port history, ticker
    - _Requirements: 5.1, 5.3, 5.6_

  - [x] 7.7 Convert options endpoints
    - Port option_chain, option_greeks, multi_option_greeks
    - Port option_symbol, options_order, options_multiorder
    - Port synthetic_future
    - _Requirements: 5.1, 5.3, 5.6_

  - [x] 7.8 Convert utility endpoints
    - Port funds, margin, instruments
    - Port search, symbol, expiry, intervals
    - Port ping
    - _Requirements: 5.1, 5.3, 5.6_

  - [x] 7.9 Convert remaining API endpoints
    - Port basket_order, split_order
    - Port analyzer, telegram_bot
    - Port chart_api, market_holidays, market_timings
    - Port pnl_symbols
    - _Requirements: 5.1, 5.3, 5.6_

  - [x] 7.10 Create unified API router
    - Create restx_api/__init__.py for FastAPI
    - Register all API routers with correct paths
    - Configure OpenAPI documentation
    - _Requirements: 5.7_

  - [x] 7.11 Apply rate limiting to API endpoints
    - Add slowapi decorators to all endpoints
    - Match Flask-Limiter rate limits exactly
    - _Requirements: 5.5_

  - [x] 7.12 Write property tests for API migration
    - **Property 5: REST API Contract Preservation**
    - **Property 6: API Response Equivalence**
    - **Property 7: Rate Limit Equivalence**
    - **Property 12: Error Response Format Equivalence**
    - **Validates: Requirements 5.1-5.7, 9.1-9.7**

- [x] 8. Checkpoint - Phase 4 Complete
  - Verify all API endpoints accessible
  - Test with existing API clients
  - Ensure all tests pass, ask the user if questions arise

- [x] 9. Phase 5: WebSocket Migration
  - [x] 9.1 Update extensions.py for FastAPI
    - Configure python-socketio with ASGI mode
    - Set up AsyncServer with same settings
    - _Requirements: 6.1_

  - [x] 9.2 Create Socket.IO ASGI app
    - Create socketio.ASGIApp wrapper
    - Mount on FastAPI app at /socket.io
    - _Requirements: 6.1_

  - [x] 9.3 Port Socket.IO event handlers
    - Port connect, disconnect events
    - Port all custom events
    - Preserve event names and payload structures
    - _Requirements: 6.2, 6.4_

  - [x] 9.4 Update websocket_proxy integration
    - Update app_integration.py for FastAPI
    - Ensure WebSocket proxy server compatibility
    - _Requirements: 6.3_

  - [x] 9.5 Port WebSocket authentication
    - Implement API key authentication for WebSocket
    - Match Flask-SocketIO auth behavior
    - _Requirements: 6.5_

  - [x] 9.6 Verify market data broadcasting
    - Test subscription and data flow
    - Verify message format matches Flask version
    - _Requirements: 6.6_

  - [x] 9.7 Write property tests for WebSocket migration
    - **Property 10: WebSocket Message Format Preservation**
    - **Validates: Requirements 6.1-6.6**

- [x] 10. Checkpoint - Phase 5 Complete
  - Verify WebSocket connections work
  - Test real-time data flow
  - Ensure all tests pass, ask the user if questions arise

- [x] 11. Phase 6: Integration and Finalization
  - [x] 11.1 Update app.py to use FastAPI
    - Replace Flask app with FastAPI app
    - Preserve all startup initialization
    - Keep setup_environment() function
    - _Requirements: 3.1, 3.4_

  - [x] 11.2 Update startup scripts
    - Update start.sh for uvicorn
    - Update Dockerfile for FastAPI
    - Update docker-compose.yaml
    - _Requirements: 3.1_

  - [x] 11.3 Verify service layer unchanged
    - Confirm services/ files only have import changes
    - Confirm database/ files only have import changes
    - Confirm broker/ files only have import changes
    - Confirm sandbox/ files only have import changes
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 11.4 Verify directory structure preserved
    - Confirm no new top-level directories
    - Confirm no directories renamed or moved
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 11.5 Run full test suite
    - Run all existing tests in test/ folder
    - Verify all tests pass
    - _Requirements: 13.1_

  - [x] 11.6 Test React frontend integration
    - Verify frontend works without code changes
    - Test all major user flows
    - _Requirements: 13.4_

  - [x] 11.7 Write integration property tests
    - **Property 11: Service Layer Immutability**
    - **Property 13: Directory Structure Preservation**
    - **Validates: Requirements 10.1-10.5, 12.1-12.6, 13.1-13.4**

- [x] 12. Final Checkpoint - Migration Complete
  - Run complete test suite
  - Verify all functionality works
  - Document any manual steps required
  - Ensure all tests pass, ask the user if questions arise

## Notes

- All tasks including property-based tests are required for comprehensive validation
- Each phase is independently testable - verify before proceeding to next phase
- Rollback for any phase: revert git changes for that phase's files
- Service layer (services/, database/, broker/, sandbox/) should remain unchanged except imports
- Frontend should work without any code changes after migration
- Property tests validate universal correctness properties across all inputs
- Unit tests validate specific examples and edge cases
