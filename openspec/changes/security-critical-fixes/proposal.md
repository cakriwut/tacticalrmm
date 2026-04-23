## Why

A code audit and live exploit confirmation revealed that multiple services in the stack have zero or broken authorization on write operations, plaintext credential storage, and hardcoded secrets shipped in frontend bundles. A DEPARTMENT_HEAD user was able to PATCH their own ES user document to escalate to SUPER_ADMIN and inject arbitrary tenant IDs — confirmed working on the dev environment. These must be fixed before the platform is exposed to production load.

## What Changes

- **gd-es-middleware**: Add authentication middleware to all write routes (`POST /documents`, `PATCH /documents`); enforce field-level blocklist preventing writes to `depRole`, `_depIds`, `_superAdmin`; add document ownership verification (caller `_id` must match document `_id` for user-doc writes).
- **gs-mgt-server**: Replace plaintext MongoDB password storage with bcrypt; migrate the `login` handler to hash-compare; run a one-time migration script to re-hash existing `users` collection passwords.
- **gs-web-app**: Immediately rotate `crawler_user` Basic Auth credentials and the hardcoded Facebook Graph API token (both are in the shipped JS bundle); remove `__ptxt` plaintext password field from change-password and add-user flows; replace SHA-1 client-side hashing with server-side bcrypt verification; move all role/permission checks server-side (eliminate `localStorage.depRole` trust).
- **DocServerV2**: Add FastAPI authentication middleware to all write routes (`POST`, `PATCH`, `DELETE`, bulk operations); the existing OPA code (`api/rego/opa.py`, `.rego` files) is **dead/orphan code** (`AUTHORIZED_MODE=false`, no OPA service deployed) — authorization must be implemented from scratch, not by fixing OPA.
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
- `gd-es-middleware`: no new deps — uses existing AuthManager
- `gs-mgt-server`: `bcrypt` npm package
- `gs-web-app`: no new deps — remove SHA-1, shift auth logic to server calls
- `DocServerV2`: no new deps — FastAPI `HTTPBearer` already available; identity from `X-Cyber-Userinfo` header (already parsed in some routes)
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
