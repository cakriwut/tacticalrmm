## ADDED Requirements

### Requirement: Write routes require authenticated identity
All write routes in gd-es-middleware (`POST /documents`, `PATCH /documents`) SHALL require a valid authenticated identity before processing. If the identity cannot be resolved from the request headers, the service SHALL return HTTP 401. The identity is resolved via `AuthManager` using the `x-auth-userid` or `x-forwarded-user` header injected by Traefik.

#### Scenario: Authenticated user can write
- **WHEN** a request with a valid `x-forwarded-user` header is sent to `POST /documents` or `PATCH /documents`
- **THEN** the service processes the request and returns 2xx

#### Scenario: Unauthenticated request is rejected
- **WHEN** a request with no `x-forwarded-user` or `x-auth-userid` header is sent to `POST /documents` or `PATCH /documents`
- **THEN** the service returns HTTP 401 and does not write to Elasticsearch

#### Scenario: Unknown user is rejected
- **WHEN** a request contains a `x-forwarded-user` value that does not match any user document in the ES `user` index
- **THEN** the service returns HTTP 401 and does not write to Elasticsearch

### Requirement: Privilege-escalation fields are stripped from write payloads
The fields `depRole`, `_depIds`, `_superAdmin` SHALL be removed from any write payload before the document is passed to Elasticsearch, unless the authenticated caller's `depRole` is `SUPER_ADMIN`.

#### Scenario: DEPARTMENT_HEAD cannot escalate their own role
- **WHEN** a DEPARTMENT_HEAD user sends `PATCH /documents` with body containing `depRole: "SUPER_ADMIN"`
- **THEN** the `depRole` field is stripped from the payload and the write proceeds without it

#### Scenario: DEPARTMENT_HEAD cannot inject fake tenant IDs
- **WHEN** a DEPARTMENT_HEAD user sends `PATCH /documents` with body containing `_depIds: ["FAKE_TENANT_999"]`
- **THEN** the `_depIds` field is stripped from the payload

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
The auth middleware and field-stripping logic SHALL have unit test coverage. Tests MUST cover: 401 on missing header, 401 on unknown user, 403 on ownership mismatch, field stripping for each blocked field, SUPER_ADMIN bypass.

#### Scenario: Unit test suite passes
- **WHEN** the test suite for gd-es-middleware write-path auth is run
- **THEN** all tests pass with zero failures
