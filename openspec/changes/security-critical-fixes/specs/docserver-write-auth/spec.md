## ADDED Requirements

### Requirement: Write routes require authenticated identity
All mutation routes in DocServerV2 (`POST /docs/{collection}`, `PATCH /docs/{collection}/{id}`, `DELETE /docs/{collection}/{id}`, `_bulkInsert`, `_bulkDelete`, `_bulkUpdate`) SHALL require a valid `X-Cyber-Userinfo` header. A `require_identity()` FastAPI dependency SHALL decode the header (base64 JSON, Traefik-injected) and return the caller identity dict. If the header is absent or cannot be decoded as JSON, the service SHALL return HTTP 401.

### Requirement: Privilege-escalation fields are blocked via `field_guard()` dependency (reject mode)
A `field_guard()` FastAPI dependency SHALL enforce a role-keyed field allowlist for write routes. For callers whose `depRole` is not `SUPER_ADMIN`, the fields `depRole`, `_depIds`, `_superAdmin`, `_id` SHALL be treated as blocked. If a blocked field is present in the request body, the service SHALL return HTTP 403 with response body `{ "error": "FIELD_WRITE_FORBIDDEN", "fields": ["<field1>", ...] }`. Fields are NOT silently stripped.

### Requirement: Pydantic discriminated models provide schema-layer defense-in-depth
For user-document write routes, the request body SHALL be validated against a role-appropriate Pydantic model:
- `UserPatchAdmin` — includes `depRole`, `_depIds`, `_superAdmin`, and all normal fields (used for SUPER_ADMIN callers)
- `UserPatchRestricted` — declares only non-privileged fields; configured with `model_config = {"extra": "forbid"}` so any unknown/privileged field causes HTTP 422

This provides a second layer of protection: even if `field_guard()` has a bug, the Pydantic model validation rejects privileged fields at the schema level.

#### Scenario: Authenticated request to write route proceeds
- **WHEN** a request with a valid `X-Cyber-Userinfo` header is sent to `PATCH /docs/{collection}/{id}`
- **THEN** the service processes the write and returns 2xx

#### Scenario: Unauthenticated request to write route is rejected
- **WHEN** a request with no `X-Cyber-Userinfo` header is sent to `PATCH /docs/{collection}/{id}`
- **THEN** the service returns HTTP 401 and does not write to the database

#### Scenario: Malformed identity header is rejected
- **WHEN** a request with a non-base64 or non-JSON `X-Cyber-Userinfo` header is sent to a write route
- **THEN** the service returns HTTP 401

#### Scenario: Non-admin cannot write privileged fields
- **WHEN** a DEPARTMENT_HEAD user sends `PATCH /docs/user/{id}` with body containing `depRole: "SUPER_ADMIN"`
- **THEN** the service returns HTTP 403 with `{ "error": "FIELD_WRITE_FORBIDDEN", "fields": ["depRole"] }`
- **AND** no write is made to the database

#### Scenario: Pydantic rejects privileged fields for restricted model
- **WHEN** a non-SUPER_ADMIN user sends a write request and the body is validated against `UserPatchRestricted`
- **AND** the body contains `depRole` or `_depIds`
- **THEN** Pydantic raises a validation error and the service returns HTTP 422

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
The `require_identity()` and `field_guard()` FastAPI dependencies, and the `UserPatchRestricted` Pydantic model, SHALL have unit test coverage. Tests MUST cover: 401 on missing header, 401 on malformed header, successful decode of valid header, 403 with correct `fields` array for each blocked field (`depRole`, `_depIds`, `_superAdmin`, `_id`) from non-admin caller, SUPER_ADMIN bypass (all fields allowed), Pydantic 422 for privileged fields on `UserPatchRestricted`, 401 on each bulk mutation route without header.

#### Scenario: Unit test suite passes
- **WHEN** the DocServerV2 write-auth test suite is run
- **THEN** all tests pass with zero failures
