## Context

A live privilege-escalation exploit was confirmed on the dev environment: a DEPARTMENT_HEAD user patched their own ES user document to set `depRole: SUPER_ADMIN` and inject arbitrary `_depIds`. The root cause spans five services with independent but compounding failures: no write-path authorization in gd-es-middleware and DocServerV2, plaintext credential storage in gs-mgt-server's MongoDB, hardcoded secrets in the gs-web-app JS bundle, and unauthenticated sensitive endpoints in authserver.

The DocServerV2 codebase contains OPA policy files (`api/rego/opa.py`, `.rego` files) but these are **dead/orphan code**: `AUTHORIZED_MODE=false` is set in the live pod, no OPA service is deployed in the `cyber` namespace, and write handlers have zero OPA calls even in the code. Authorization for DocServerV2 writes must be built from scratch.

Stack: Azure Kubernetes (`cyber` namespace), Traefik ingress with `traefik-forward-auth` + Keycloak. Auth headers injected at ingress: `X-Forwarded-User`, `X-Cyber-Userinfo` (base64 JSON), `X-Cyber-OidcToken`, `X-Cyber-AccessToken`.

## Goals / Non-Goals

**Goals:**
- Block the confirmed P0 exploit path (unauthenticated PATCH to ES user doc with role escalation fields)
- Replace plaintext MongoDB passwords with bcrypt in gs-mgt-server
- Rotate credentials already exposed in the gs-web-app JS bundle
- Gate `POST /license/import/csv` in authserver behind authentication
- Add write-path authorization to DocServerV2 using identity headers already injected by Traefik

**Non-Goals:**
- Full OAuth2/JWT introspection refactor (out of scope — ingress handles token verification)
- Rebuilding SHA-1 login flow end-to-end (tracked separately under `web-app-credential-hygiene` as P1)
- Deploying a new OPA server — the fix does NOT use OPA
- Changing the Traefik / Keycloak auth pipeline
- Fixing pre-existing test gaps unrelated to the security findings

## Decisions

### D1 — Write-path auth in gd-es-middleware: reuse existing AuthManager, not a new JWT validator

**Decision**: Instantiate `AuthManager` at the start of `updateDocument()` and `saveDocument()` controllers and call `validate()` before proceeding.

**Rationale**: AuthManager already exists in the codebase (`src/core_modules/gs-auth/`), reads `x-auth-userid` / `x-forwarded-user` (injected by Traefik), looks up the user ES doc, and returns the validated identity. Reusing it is the minimal, consistent change. No new dependencies needed.

**Alternative considered**: Verify bearer token against Keycloak introspection endpoint. Rejected — authserver calls Keycloak Admin API (remote call overhead), and the existing `x-forwarded-user` header is already verified by `traefik-forward-auth` before reaching the service. Adding a second remote call adds latency and a new failure mode.

### D2 — Field blocklist in gd-es-middleware: strip at controller layer

**Decision**: Before passing `req.body` to `elastic.updateDocument()`, strip the fields `depRole`, `_depIds`, `_superAdmin`, `_id` from the update payload unless the caller's `depRole` is `SUPER_ADMIN`.

**Rationale**: Ownership check (D3) prevents cross-user writes; the field blocklist prevents a legitimate user from escalating their own role. Defense-in-depth.

**Alternative considered**: Schema validation with JSON Schema. More thorough but heavier to retrofit; blocklist is sufficient for the specific exploit vectors identified.

### D3 — Ownership check in gd-es-middleware: `_id` in body must match authenticated user's ES doc ID

**Decision**: For writes to the `user` datasource (`_dataSource: "user"`), assert that `req.body._id === authManager.userDoc._id`.

**Rationale**: Prevents DEPARTMENT_HEAD from patching another user's document, even without role escalation.

### D4 — bcrypt migration in gs-mgt-server: dual-read during rollout, then cut over

**Decision**: Deploy a migration script that re-hashes all existing `users` collection passwords. New login handler: hash incoming plaintext with bcrypt, compare to stored hash. Dual-read not needed — migration runs before service restart.

**Rationale**: The `users` collection is small (application admin accounts only). A one-shot migration is simpler than dual-read. Schedule during a maintenance window or low-traffic period.

**Risk**: If migration script fails mid-run, some accounts have bcrypt and some have plaintext. Mitigation: run migration in a transaction-like loop with per-document error handling; keep a backup.

### D5 — DocServerV2 write auth: identity from `X-Cyber-Userinfo` header, 401 if absent

**Decision**: Add a FastAPI dependency function `require_identity()` that decodes the `X-Cyber-Userinfo` header (base64 JSON, already injected by Traefik). Inject it into `create_document`, `update_document`, `delete_document`, `bulk_insert`, `bulk_delete`, `bulk_update` route handlers. Return HTTP 401 if header is absent or malformed. Delete the orphan OPA files (`api/rego/opa.py`, `api/policies/`) as part of this PR.

**Rationale**: `X-Cyber-Userinfo` is already parsed in Trino connector routes — reuse the same pattern. Deleting dead OPA code reduces confusion and future audit surface.

**Alternative considered**: Keep OPA, deploy a standalone OPA sidecar. Rejected — OPA was never deployed in production, and deploying a new sidecar to every DocServerV2 replica is disproportionate to the goal of gating writes.

### D6 — authserver `/license/import/csv`: add `validate_token` dependency

**Decision**: Add the existing `validate_token` FastAPI dependency to the `POST /license/import/csv` route.

**Rationale**: Consistent with how `/me`, `/sessions` are protected. Minimal change.

### D7 — Credential rotation: out-of-band, before code changes merge

**Decision**: Rotate `crawler_user` password and Facebook token immediately via secrets management (Kubernetes secrets / Doppler), independent of the code PR.

**Rationale**: The credentials are already public in git history and shipped bundles. Code changes are slower than secret rotation. Rotation must happen first.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| bcrypt migration corrupts user accounts | Run on a DB backup first; add per-document error handling; keep plaintext backup for 1 sprint |
| gd-es-middleware AuthManager rejects valid users with `ES_MIDDLEWARE_AUTH_ENABLE=false` in some envs | Check flag value per env before deploying; if false, auth is explicitly disabled — flag this to team |
| DocServerV2 401 on internal service-to-service calls that don't pass `X-Cyber-Userinfo` | Audit internal callers before deploy; internal calls may need to forward the header |
| Traefik header stripping — `x-forwarded-user` could be spoofed if Traefik misconfigured | Verify Traefik strips incoming `X-Forwarded-User` before injecting its own (P1.3 in SECURITY_VERIFICATION.md) |
| Dead OPA files deleted — someone assumes OPA is available | Document explicitly in PR and service README |

## Migration Plan

1. **Immediate (this week)**: Rotate `crawler_user` and Facebook Graph token out-of-band. Update Kubernetes secrets. Verify services function normally.
2. **Sprint 1**: gd-es-middleware write-path auth (D1–D3). Deploy to dev, run integration test (exploit path must return 401/403). Deploy to staging.
3. **Sprint 1**: authserver hardening (D6) + CORS fix + disable `/docs`. Low-risk, deploy alongside gd-es-middleware.
4. **Sprint 2**: gs-mgt-server bcrypt migration. Maintenance window: run migration script, verify all accounts, deploy new login handler.
5. **Sprint 2**: DocServerV2 write auth (D5). Audit internal callers first. Deploy with `X-Cyber-Userinfo` header forwarding confirmed.
6. **Sprint 3**: gs-web-app credential hygiene — remove `__ptxt`, eliminate SHA-1 client-side (requires parallel server-side change in gs-mgt-server to accept bcrypt-verified login).

## Open Questions

- Q1: Does any internal service make direct unauthenticated calls to DocServerV2 write endpoints? (Need caller audit before Sprint 2 deploy.)
- Q2: What is `ES_MIDDLEWARE_AUTH_ENABLE` set to in staging and production? (Determines whether D1 auth is actually enforced post-deploy in each env.)
- Q3: Can the Facebook Graph API token scope be restricted to read-only on the FB side, or must it be fully rotated?
