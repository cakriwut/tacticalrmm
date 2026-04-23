## ADDED Requirements

### Requirement: Write routes require authenticated identity
All write routes in gd-es-middleware (`POST /documents`, `PATCH /documents`) SHALL require a valid authenticated identity before processing. Identity SHALL be resolved from the `X-Cyber-Userinfo` header (base64 JSON, injected by Traefik) via a `parseIdentity` middleware that populates `res.locals.user`. If the header is absent or cannot be base64-decoded as JSON, the service SHALL return HTTP 401. The resolved username SHALL then be validated against the ES `user` index via `AuthManager`; if no matching user document exists, the service SHALL return HTTP 401.

#### Scenario: Authenticated user can write
- **WHEN** a request with a valid `x-forwarded-user` header is sent to `POST /documents` or `PATCH /documents`
- **THEN** the service processes the request and returns 2xx

#### Scenario: Unauthenticated request is rejected
- **WHEN** a request with no `x-forwarded-user` or `x-auth-userid` header is sent to `POST /documents` or `PATCH /documents`
- **THEN** the service returns HTTP 401 and does not write to Elasticsearch

#### Scenario: Unknown user is rejected
- **WHEN** a request contains a `x-forwarded-user` value that does not match any user document in the ES `user` index
- **THEN** the service returns HTTP 401 and does not write to Elasticsearch

### Requirement: Privilege-escalation fields are blocked from write payloads (reject mode)
The fields `depRole`, `_depIds`, `_superAdmin`, `_id` SHALL be treated as privileged write fields. A `fieldGuard` middleware SHALL enforce a role-keyed allowlist in **reject mode**: if a caller whose `depRole` is not `SUPER_ADMIN` submits any of these fields, the service SHALL return HTTP 403 with response body `{ "error": "FIELD_WRITE_FORBIDDEN", "fields": ["<field1>", ...] }`. The request SHALL NOT be forwarded to Elasticsearch. Fields are NOT silently stripped.

The allowlist is:
- `SUPER_ADMIN`: may write `depRole`, `_depIds`, `_superAdmin`, `_id`, plus all normal fields
- `DEPARTMENT_HEAD`: may write `email`, `displayName` only
- `MEMBER` / default: may write `displayName` only

#### Scenario: DEPARTMENT_HEAD cannot escalate their own role
- **WHEN** a DEPARTMENT_HEAD user sends `PATCH /documents` with body containing `depRole: "SUPER_ADMIN"`
- **THEN** the service returns HTTP 403 with `{ "error": "FIELD_WRITE_FORBIDDEN", "fields": ["depRole"] }`
- **AND** no write is made to Elasticsearch

#### Scenario: DEPARTMENT_HEAD cannot inject fake tenant IDs
- **WHEN** a DEPARTMENT_HEAD user sends `PATCH /documents` with body containing `_depIds: ["FAKE_TENANT_999"]`
- **THEN** the service returns HTTP 403 with `{ "error": "FIELD_WRITE_FORBIDDEN", "fields": ["_depIds"] }`
- **AND** no write is made to Elasticsearch

#### Scenario: SUPER_ADMIN can write privileged fields
- **WHEN** a SUPER_ADMIN user sends `PATCH /documents` with body containing `depRole: "DEPARTMENT_HEAD"`
- **THEN** the `depRole` field is retained and the write proceeds normally

### Requirement: User-document writes enforce ownership
For writes where `_dataSource` is `"user"`, the `_id` field in the request body SHALL match the authenticated caller's user document `_id`. If they do not match, the service SHALL return HTTP 403.

#### Scenario: User can patch their own document
- **WHEN** an authenticated user sends `PATCH /documents` with `_dataSource: "user"` and `_id` matching their own user document ID
- **THEN** the write proceeds normally

#### Scenario: User cannot patch another user's document
- **WHEN** an authenticated user sends `PATCH /documents` with `_dataSource: "user"` and `_id` not matching their own user document ID
- **THEN** the service returns HTTP 403 and does not write to Elasticsearch

### Requirement: Write-path auth unit tests
The `parseIdentity`, `fieldGuard`, `validateUser`, and `ownershipCheck` middleware functions SHALL have unit test coverage. Tests MUST cover: 401 on missing `X-Cyber-Userinfo` header, 401 on malformed header, 401 on unknown user (no ES doc), 403 on ownership mismatch, 403 with correct `fields` array for each blocked field (`depRole`, `_depIds`, `_superAdmin`, `_id`), SUPER_ADMIN bypass (all fields allowed).

#### Scenario: Unit test suite passes
- **WHEN** the test suite for gd-es-middleware write-path auth is run
- **THEN** all tests pass with zero failures
