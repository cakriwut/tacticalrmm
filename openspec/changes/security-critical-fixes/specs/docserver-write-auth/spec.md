## ADDED Requirements

### Requirement: Write routes require authenticated identity
All mutation routes in DocServerV2 (`POST /docs/{collection}`, `PATCH /docs/{collection}/{id}`, `DELETE /docs/{collection}/{id}`, `_bulkInsert`, `_bulkDelete`, `_bulkUpdate`) SHALL require a valid `X-Cyber-Userinfo` header. If the header is absent or cannot be decoded as base64 JSON, the service SHALL return HTTP 401.

#### Scenario: Authenticated request to write route proceeds
- **WHEN** a request with a valid `X-Cyber-Userinfo` header is sent to `PATCH /docs/{collection}/{id}`
- **THEN** the service processes the write and returns 2xx

#### Scenario: Unauthenticated request to write route is rejected
- **WHEN** a request with no `X-Cyber-Userinfo` header is sent to `PATCH /docs/{collection}/{id}`
- **THEN** the service returns HTTP 401 and does not write to the database

#### Scenario: Malformed identity header is rejected
- **WHEN** a request with a non-base64 or non-JSON `X-Cyber-Userinfo` header is sent to a write route
- **THEN** the service returns HTTP 401

### Requirement: OPA dead code removed
The files `api/rego/opa.py`, `api/policies/policy.rego`, and `api/policies/accesscontrol.rego` SHALL be deleted. The `AUTHORIZED_MODE` environment variable and any references to it in the codebase SHALL be removed. This eliminates orphan code that was never deployed and reduces audit surface.

#### Scenario: OPA files do not exist in the repository after fix
- **WHEN** the repository is scanned for OPA-related files
- **THEN** no `.rego` files, `opa.py`, or `AUTHORIZED_MODE` references are found

### Requirement: Bulk mutation routes require authenticated identity
The bulk operation routes (`_bulkInsert`, `_bulkDelete`, `_bulkUpdate`) SHALL apply the same identity requirement as single-document write routes.

#### Scenario: Unauthenticated bulk insert is rejected
- **WHEN** a request with no `X-Cyber-Userinfo` header is sent to `_bulkInsert`
- **THEN** the service returns HTTP 401

### Requirement: Write-path auth unit tests
The `require_identity()` FastAPI dependency SHALL have unit test coverage. Tests MUST cover: 401 on missing header, 401 on malformed header, successful decode of valid header, 401 on each bulk mutation route without header.

#### Scenario: Unit test suite passes
- **WHEN** the DocServerV2 write-auth test suite is run
- **THEN** all tests pass with zero failures
