## ADDED Requirements

### Requirement: License import endpoint requires authentication
The `POST /license/import/csv` route in authserver SHALL require a valid authenticated session. Unauthenticated requests SHALL be rejected with HTTP 401. The existing `validate_token` FastAPI dependency SHALL be applied to this route.

#### Scenario: Authenticated request can import license CSV
- **WHEN** an authenticated admin sends `POST /license/import/csv` with a valid session cookie/header
- **THEN** the license data is imported and the service returns 2xx

#### Scenario: Unauthenticated request to import endpoint is rejected
- **WHEN** a request without authentication sends `POST /license/import/csv`
- **THEN** the service returns HTTP 401 and does not modify license data

### Requirement: CORS restricted to explicit allowlist
The authserver CORS configuration SHALL NOT use `allow_origins=["*"]`. The allowed origins SHALL be set to the known frontend origins (e.g., the application domain). `allow_credentials=True` SHALL only be used with explicit, non-wildcard origins.

#### Scenario: Request from unknown origin is rejected by CORS
- **WHEN** a browser sends a cross-origin request from an unlisted origin
- **THEN** the CORS preflight response does not include `Access-Control-Allow-Origin` for that origin

#### Scenario: Request from allowed origin proceeds
- **WHEN** a browser sends a cross-origin request from the configured allowed origin
- **THEN** the CORS headers are set correctly and the request proceeds

### Requirement: API documentation disabled in production
The FastAPI auto-generated `/docs` (Swagger UI) and `/redoc` endpoints SHALL be disabled in the production environment. They MAY remain enabled in non-production environments.

#### Scenario: /docs returns 404 in production
- **WHEN** a request is sent to `/docs` in the production environment
- **THEN** the service returns HTTP 404

#### Scenario: /docs is available in development
- **WHEN** a request is sent to `/docs` in the development environment
- **THEN** the Swagger UI is returned (optional, for developer convenience)

### Requirement: Authserver hardening unit tests
Tests SHALL verify: 401 on unauthenticated `/license/import/csv`, CORS rejection of unlisted origins.

#### Scenario: Unit test suite passes
- **WHEN** the authserver hardening test suite is run
- **THEN** all tests pass with zero failures
