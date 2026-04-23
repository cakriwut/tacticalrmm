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

### D1 — Write-path auth in gd-es-middleware: `parseIdentity` middleware + `fieldGuard` middleware (Option A)

**Decision**: Add two Express middleware functions to all write routes: (1) `parseIdentity` decodes `X-Cyber-Userinfo` (base64 JSON) into `res.locals.user`; (2) `fieldGuard` enforces a role-keyed field allowlist in **reject mode** (returns 403, does not silently strip). Also instantiate `AuthManager` to validate the resolved username against the ES `user` index and confirm the user exists.

Route registration:
```typescript
router.patch('/documents', parseIdentity, validateUser, fieldGuard, ownershipCheck, updateDocument);
router.post('/documents',  parseIdentity, validateUser, fieldGuard, saveDocument);
```

Field allowlist:
```typescript
const WRITE_POLICY = {
  SUPER_ADMIN:     new Set(['depRole', '_depIds', '_superAdmin', 'email', 'displayName', 'isActive', ...]),
  DEPARTMENT_HEAD: new Set(['email', 'displayName']),
  MEMBER:          new Set(['displayName']),
};
// Any field NOT in the caller's allowed set → HTTP 403 { error: 'FIELD_WRITE_FORBIDDEN', fields: [...] }
```

**Rationale**: Reject mode (not strip mode) is chosen because silent stripping hides the error from the client and makes debugging harder. Explicit 403 forces callers to be correct and is auditable. `parseIdentity` reads from the Traefik-injected header — never from `req.body` — so the identity source cannot be forged via the request payload.

**Alternative considered**: Reuse existing `AuthManager.validate()` as the sole guard. Rejected as insufficient — `AuthManager` validates identity but has no field-level write policy. Both layers are required: identity verification AND field allowlist.

**Alternative considered**: Verify bearer token against Keycloak introspection endpoint. Rejected — adds 20–150ms RTT + Keycloak load. `traefik-forward-auth` already verified the token at ingress; `X-Cyber-Userinfo` reflects the verified identity.

### D2 — Field blocklist in gd-es-middleware: reject mode, not strip mode

**Decision**: `fieldGuard` middleware computes the set of submitted fields that the caller's role is not permitted to write. If the set is non-empty, return HTTP 403 with `{ error: "FIELD_WRITE_FORBIDDEN", fields: ["depRole", ...] }`. Do NOT silently strip fields.

Blocked fields for non-SUPER_ADMIN: `depRole`, `_depIds`, `_superAdmin`, `_id`.

**Rationale**: Reject mode makes the security boundary visible to callers and auditable in logs. Silent stripping hides misconfigured clients; reject forces them to send only what they're allowed to. Defense-in-depth: ownership check (D3) prevents cross-user writes; the field blocklist prevents a legitimate user from escalating their own role in the same call.

**Alternative considered**: Strip blocked fields and proceed silently. Rejected — harder to audit, hides bugs in calling clients, and provides no signal to detect exploit attempts.

### D3 — Ownership check in gd-es-middleware: `_id` in body must match authenticated user's ES doc ID

**Decision**: For writes to the `user` datasource (`_dataSource: "user"`), assert that `req.body._id === authManager.userDoc._id`.

**Rationale**: Prevents DEPARTMENT_HEAD from patching another user's document, even without role escalation.

### D4 — bcrypt migration in gs-mgt-server: dual-read during rollout, then cut over

**Decision**: Deploy a migration script that re-hashes all existing `users` collection passwords. New login handler: hash incoming plaintext with bcrypt, compare to stored hash. Dual-read not needed — migration runs before service restart.

**Rationale**: The `users` collection is small (application admin accounts only). A one-shot migration is simpler than dual-read. Schedule during a maintenance window or low-traffic period.

**Risk**: If migration script fails mid-run, some accounts have bcrypt and some have plaintext. Mitigation: run migration in a transaction-like loop with per-document error handling; keep a backup.

### D5 — DocServerV2 write auth: `require_identity()` + `field_guard()` FastAPI dependencies + Pydantic discriminated models

**Decision**: Three-layer authorization for DocServerV2 writes:

1. **`require_identity()` dependency** — decodes `X-Cyber-Userinfo` header (base64 JSON, Traefik-injected). Returns 401 if absent or malformed. Reuses the same decode pattern already used in Trino connector routes.

2. **`field_guard()` dependency** — enforces role-keyed field blocklist (same policy as gd-es-middleware). For user-document writes, blocks `depRole`, `_depIds`, `_superAdmin`, `_id` for non-SUPER_ADMIN callers. Returns 403 with `{"error": "FIELD_WRITE_FORBIDDEN", "fields": [...]}`.

3. **Pydantic discriminated models** (defense-in-depth) — `UserPatchAdmin` (all fields) vs `UserPatchRestricted` (`extra="forbid"`, no privileged fields declared). The correct model is selected based on caller role. Even if a middleware bug allows a request through, Pydantic raises HTTP 422 if a blocked field is present in `UserPatchRestricted`.

Route pattern:
```python
@router.patch("/docs/{collection}/{id}")
async def update_document(
    collection: str, id: str,
    caller: dict = Depends(require_identity),
    body: dict = Depends(field_guard),
):
    ...
```

Delete orphan OPA files (`api/rego/opa.py`, `api/policies/policy.rego`, `api/policies/accesscontrol.rego`) and all `AUTHORIZED_MODE` references in the same PR.

**Rationale**: Three layers ensure no single point of failure. `require_identity` gates the request. `field_guard` applies role policy. Pydantic model catches schema-level bypasses. `X-Cyber-Userinfo` decode reuses the existing pattern in the codebase — no new library needed.

**Alternative considered**: Keep OPA, deploy a standalone OPA sidecar. Rejected — OPA was never deployed in production; deploying a new sidecar adds operational overhead disproportionate to the goal. Inline Python policy is correct for a single service.

**Alternative considered**: Keycloak introspection per write request. Rejected — adds network latency; ingress already verified the token. Trusted header is sufficient when Traefik is the only ingress and network policy enforces it.

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
