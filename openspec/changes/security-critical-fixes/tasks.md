## 1. Immediate — Credential Rotation (pre-code, all environments)

- [ ] 1.1 Rotate `crawler_user` password — update the Kubernetes secret / Doppler entry in all environments (dev, staging, prod); verify gs-web-app crawler calls still work after rotation
- [ ] 1.2 Revoke and replace the Facebook Graph API token `6628568379|c1e620fa708a1d5696fb991c1bde5662` — update the Kubernetes secret / Doppler entry; verify any FB-dependent features in all environments
- [ ] 1.3 Remove hardcoded `crawler_user` Basic Auth from `gs-web-app/app/src/api/axios.js` — replace with runtime env var injected at build or via server-side proxy
- [ ] 1.4 Remove hardcoded Facebook token from `gs-web-app/app/src/common/config.js` — replace with runtime env var or server-side proxy call
- [ ] 1.5 Verify no other hardcoded secrets remain in the gs-web-app bundle (scan: `grep -r "password\|token\|secret\|k2Zs" app/src/`)

## 2. gd-es-middleware — Write-Path Authentication (Option A: Field Blocklist Middleware)

- [ ] 2.1 Implement `parseIdentity` middleware (`src/middleware/parseIdentity.ts`) — decode `X-Cyber-Userinfo` header (base64 JSON) into `res.locals.user`; return HTTP 401 if header absent or malformed
- [ ] 2.2 Implement `validateUser` middleware (`src/middleware/validateUser.ts`) — instantiate `AuthManager` with resolved username; call `validate()`; return HTTP 401 if user doc not found in ES `user` index
- [ ] 2.3 Implement `fieldGuard` middleware (`src/middleware/fieldGuard.ts`) — role-keyed allowlist in **reject mode**: blocked fields `depRole`, `_depIds`, `_superAdmin`, `_id` for non-SUPER_ADMIN callers; return HTTP 403 `{ error: "FIELD_WRITE_FORBIDDEN", fields: [...] }` (do NOT strip silently)
- [ ] 2.4 Implement `ownershipCheck` middleware (`src/middleware/ownershipCheck.ts`) — for `_dataSource: "user"` writes, assert `req.body._id === res.locals.user.userDoc._id`; return HTTP 403 on mismatch
- [ ] 2.5 Register middleware chain on all write routes in `documents.router.ts`: `router.patch('/documents', parseIdentity, validateUser, fieldGuard, ownershipCheck, updateDocument)` and `router.post('/documents', parseIdentity, validateUser, fieldGuard, saveDocument)`
- [ ] 2.6 Write unit tests for all 4 middleware: 401 on missing/malformed `X-Cyber-Userinfo`, 401 on unknown user, 403 `FIELD_WRITE_FORBIDDEN` for each blocked field (`depRole`, `_depIds`, `_superAdmin`, `_id`), SUPER_ADMIN bypass (all fields pass), 403 on ownership mismatch for `_dataSource: "user"`
- [ ] 2.7 Integration test: confirm the original exploit path (`PATCH /documents` with `depRole: SUPER_ADMIN` as DEPARTMENT_HEAD) returns HTTP 403 with `fields: ["depRole"]`
- [ ] 2.8 Run `lsp_diagnostics` / TypeScript build on changed files — zero errors before merge

## 3. gs-mgt-server — bcrypt Password Storage

- [ ] 3.1 Add `bcrypt` npm package to `package.json`
- [ ] 3.2 Write one-time migration script (`scripts/migrate-passwords.js`) — for each user in MongoDB `users` collection with non-bcrypt password, hash with bcrypt (cost 12), update document; skip already-bcrypt records (`$2b$` prefix)
- [ ] 3.3 Test migration script against a dev DB backup — verify all accounts can log in after migration
- [ ] 3.4 Update `dataHandler.js::login()` — replace plaintext `find({password: req.body.password})` with: `find({username})` then `bcrypt.compare(req.body.password, user.password)` 
- [ ] 3.5 Write unit tests for the new login handler: correct password succeeds, incorrect password returns 401, bcrypt compare is called (not string equality)
- [ ] 3.6 Write unit tests for migration script: idempotency (already-bcrypt record untouched), plaintext record is migrated correctly
- [ ] 3.7 Schedule and run migration script in dev → staging → prod (maintenance window); verify all user logins work after each environment

## 4. DocServerV2 — Write-Path Authentication + OPA Dead Code Removal (Option A: FastAPI Depends + Pydantic)

- [ ] 4.1 Audit all internal callers of DocServerV2 write routes — confirm they pass `X-Cyber-Userinfo` header (or document which ones don't and need updating before deploy)
- [ ] 4.2 Implement `require_identity()` FastAPI dependency (`api/deps/auth.py`) — decode `X-Cyber-Userinfo` header (base64 JSON); return HTTP 401 if absent or malformed; reuse decode pattern from Trino connector routes
- [ ] 4.3 Implement `field_guard()` FastAPI dependency (`api/deps/auth.py`) — role-keyed blocklist in **reject mode**: blocked fields `depRole`, `_depIds`, `_superAdmin`, `_id` for non-SUPER_ADMIN callers; return HTTP 403 `{ "error": "FIELD_WRITE_FORBIDDEN", "fields": [...] }`
- [ ] 4.4 Implement Pydantic models `UserPatchAdmin` and `UserPatchRestricted` (`api/models/user_patch.py`) — `UserPatchRestricted` declares only non-privileged fields with `model_config = {"extra": "forbid"}`
- [ ] 4.5 Inject `require_identity` + `field_guard` dependencies into `create_document` route handler
- [ ] 4.6 Inject `require_identity` + `field_guard` dependencies into `update_document` (PATCH) route handler; apply `UserPatchAdmin` / `UserPatchRestricted` model based on caller role
- [ ] 4.7 Inject `require_identity` + `field_guard` dependencies into `delete_document` route handler
- [ ] 4.8 Inject `require_identity` + `field_guard` dependencies into `_bulkInsert`, `_bulkDelete`, `_bulkUpdate` route handlers
- [ ] 4.9 Delete dead OPA code: `api/rego/opa.py`, `api/policies/policy.rego`, `api/policies/accesscontrol.rego`
- [ ] 4.10 Remove `AUTHORIZED_MODE` env var references from `config.py` and all route handlers
- [ ] 4.11 Write unit tests for `require_identity()` and `field_guard()`: 401 on missing/malformed header, 403 `FIELD_WRITE_FORBIDDEN` for each blocked field, SUPER_ADMIN bypass, Pydantic 422 for privileged fields on `UserPatchRestricted`, 401 on each bulk mutation route without header
- [ ] 4.12 Integration test: confirm `PATCH /docs/{collection}/{id}` without `X-Cyber-Userinfo` returns 401; with DEPARTMENT_HEAD + `depRole` field returns 403
- [ ] 4.13 Run pytest on changed files — zero failures before merge

## 5. authserver — Endpoint Hardening

- [ ] 5.1 Add `validate_token` FastAPI dependency to `POST /license/import/csv` route — return 401 for unauthenticated requests
- [ ] 5.2 Replace `allow_origins=["*"]` CORS config with explicit allowlist of known frontend origins (sourced from env var `ALLOWED_ORIGINS`)
- [ ] 5.3 Disable FastAPI `/docs` and `/redoc` endpoints in production — gate on `ENVIRONMENT != "production"` env var check in `main.py`
- [ ] 5.4 Write unit tests: 401 on unauthenticated `/license/import/csv`, CORS rejection of unlisted origin
- [ ] 5.5 Deploy to dev and staging — verify `/license/import/csv` rejects unauthenticated calls and `/docs` is inaccessible in prod config

## 6. gs-web-app — Credential Hygiene (P1, Sprint 3)

- [ ] 6.1 Remove `__ptxt` field from `ChangePassword.vue` request payload (line 89)
- [ ] 6.2 Remove `__ptxt` field from `AddUser.vue` request payload (line 479)
- [ ] 6.3 Remove SHA-1 hashing calls from `GSLogin.vue` (line 143), `ChangePassword.vue` (lines 87, 141), `AddUser.vue` (line 474) — requires `mgt-server-password-hashing` deployed first
- [ ] 6.4 Move permission checks out of `PermissionManager.js` localStorage-only path — each privileged action SHALL make a server-side authorization call; localStorage state is for UI rendering only
- [ ] 6.5 Update `utils.js::isAdmin()` to validate against server response, not `localStorage.depRole`
- [ ] 6.6 Write integration test: verify admin API calls return 403 for non-admin users even when localStorage is manually set to `depRole: SUPER_ADMIN`

## 7. Quality Gates

- [ ] 7.1 All unit tests pass (zero failures) for each service modified (2.6, 3.5, 3.6, 4.11, 5.4, 6.6)
- [ ] 7.2 Integration test confirms original P0 exploit path returns 401/403 on dev and staging
- [ ] 7.3 `lsp_diagnostics` / build clean on all modified TypeScript files (gd-es-middleware)
- [ ] 7.4 pytest clean on all modified Python files (DocServerV2, authserver)
- [ ] 7.5 Credential rotation verified in all environments before any code changes merge
- [ ] 7.6 PR review includes security checklist: no new plaintext secrets, no `as any` / type suppression, auth middleware verified on all listed routes
