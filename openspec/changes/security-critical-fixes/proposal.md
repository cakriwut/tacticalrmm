## Why

A code audit and live exploit confirmation revealed that multiple services in the stack have zero or broken authorization on write operations, plaintext credential storage, and hardcoded secrets shipped in frontend bundles. A DEPARTMENT_HEAD user was able to PATCH their own ES user document to escalate to SUPER_ADMIN and inject arbitrary tenant IDs — confirmed working on the dev environment. These must be fixed before the platform is exposed to production load.

## Authorization Approach

The chosen authorization pattern is **Option A — Field Blocklist Middleware** (stateless, no new infrastructure, directly closes the exploit vector):

- **Identity source**: Traefik-injected `X-Cyber-Userinfo` (base64 JSON) / `x-forwarded-user` headers. These are set by `traefik-forward-auth` after Keycloak token verification — services trust them as the verified identity, no additional JWT introspection needed.
- **Middleware layer** (gd-es-middleware / Express): `parseIdentity` decodes `X-Cyber-Userinfo` → `res.locals.user`; `fieldGuard` computes forbidden fields from a role-keyed allowlist and returns `HTTP 403` with `{error: "FIELD_WRITE_FORBIDDEN", fields: [...]}` if any blocked field is in the body (reject mode, not strip mode).
- **Dependency injection** (DocServerV2 / FastAPI): `require_identity()` dependency decodes `X-Cyber-Userinfo` → caller identity dict; `field_guard()` dependency enforces role-keyed blocklist; **Pydantic discriminated models** (`UserPatchAdmin` vs `UserPatchRestricted` with `extra: "forbid"`) provide schema-layer defense-in-depth so even a middleware bypass can't write blocked fields.
- **Ownership check** (secondary, alongside): for writes to the `user` datasource, `_id` in body must match authenticated caller's ES doc `_id`. Prevents cross-user mutations independently of the role check.

The **rejected alternatives** were:
- Keycloak token introspection per request — adds 20–150ms RTT + Keycloak load; ingress already verified the token.
- OPA sidecar — dead code today, 2+ weeks to deploy, disproportionate to the scope.
- ABAC — right long-term architecture if cross-tenant policy grows, but overkill for this specific field-write exploit.

## What Changes

- **gd-es-middleware**: Add `parseIdentity` + `fieldGuard` Express middleware to all write routes (`POST /documents`, `PATCH /documents`). `fieldGuard` uses a role-keyed allowlist in reject mode — blocked fields: `depRole`, `_depIds`, `_superAdmin`, `_id` (for non-SUPER_ADMIN callers). Add `ownershipCheck` middleware for `_dataSource: "user"` writes.
- **gs-mgt-server**: Replace plaintext MongoDB password storage with bcrypt; migrate the `login` handler to hash-compare; run a one-time migration script to re-hash existing `users` collection passwords.
- **gs-web-app**: Immediately rotate `crawler_user` Basic Auth credentials and the hardcoded Facebook Graph API token (both are in the shipped JS bundle); remove `__ptxt` plaintext password field from change-password and add-user flows; replace SHA-1 client-side hashing with server-side bcrypt verification; move all role/permission checks server-side (eliminate `localStorage.depRole` trust).
- **DocServerV2**: Add `require_identity()` + `field_guard()` FastAPI dependencies to all write routes (`POST`, `PATCH`, `DELETE`, bulk operations). Add Pydantic discriminated models (`UserPatchAdmin` / `UserPatchRestricted` with `extra: "forbid"`) for schema-layer defense-in-depth. The existing OPA code (`api/rego/opa.py`, `.rego` files) is **dead/orphan code** (`AUTHORIZED_MODE=false`, no OPA service deployed) — delete it as part of this PR.
- **authserver**: Add authentication dependency to `POST /license/import/csv`; restrict CORS from `allow_origins=["*"]` to explicit allowlist; disable FastAPI `/docs` and `/redoc` in production.

## Capabilities

### New Capabilities

- `es-middleware-write-auth`: Authentication and field-level authorization guard for all gd-es-middleware write routes
- `mgt-server-password-hashing`: Bcrypt password storage and verification for gs-mgt-server MongoDB user accounts
- `web-app-credential-hygiene`: Secret rotation, plaintext removal, and server-side auth migration for gs-web-app
- `docserver-write-auth`: FastAPI authentication middleware for all DocServerV2 write/mutation routes (built from scratch — no OPA)
- `authserver-hardening`: Auth gate on sensitive authserver endpoints plus CORS and docs lockdown

### Modified Capabilities

<!-- No existing specs to modify -->

## Impact

**Services modified**: `gd-es-middleware` (Node.js/TypeScript), `gs-mgt-server` (Node.js), `gs-web-app` (Vue 2), `DocServerV2` (FastAPI/Python), `authserver` (FastAPI/Python)

**Dependencies introduced**:
- `gd-es-middleware`: no new deps — `parseIdentity` + `fieldGuard` are pure middleware functions using existing AuthManager and header parsing
- `gs-mgt-server`: `bcrypt` npm package
- `gs-web-app`: no new deps — remove SHA-1, shift auth logic to server calls
- `DocServerV2`: no new deps — `require_identity()` + `field_guard()` use FastAPI `Depends()` with `Header()`; Pydantic already available; `X-Cyber-Userinfo` decode reuses existing pattern from Trino connector routes
- `authserver`: no new deps

**Data migration required**: One-time bcrypt migration of `gs-mgt-server` MongoDB `users.password` field (plaintext → bcrypt hash). Requires maintenance window or rolling migration with dual-read support.

**Breaking changes**: None to external API contracts. Internal behavior change: write requests without valid identity headers will return 401/403 instead of succeeding silently.

**Credential rotation (immediate, pre-code-fix)**:
- `crawler_user` Basic Auth password (hardcoded in `gs-web-app/app/src/api/axios.js`)
- Facebook Graph API token `6628568379|c1e620fa708a1d5696fb991c1bde5662` (hardcoded in `gs-web-app/app/src/common/config.js`)

**Quality gates**:
- Unit tests required for each auth middleware/guard (see tasks.md)
- Integration test: verify exploit path (`PATCH /documents` with `depRole: SUPER_ADMIN`) returns 401/403 post-fix
- CI must pass on all modified services before merge
- Credential rotation must be verified in all environments before shipping code changes
