## 1. Immediate — Credential Rotation (pre-code, all environments)

- [ ] 1.1 Rotate `crawler_user` password — update the Kubernetes secret / Doppler entry in all environments (dev, staging, prod); verify gs-web-app crawler calls still work after rotation
- [ ] 1.2 Revoke and replace the Facebook Graph API token `6628568379|c1e620fa708a1d5696fb991c1bde5662` — update the Kubernetes secret / Doppler entry; verify any FB-dependent features in all environments
- [ ] 1.3 Remove hardcoded `crawler_user` Basic Auth from `gs-web-app/app/src/api/axios.js` — replace with runtime env var injected at build or via server-side proxy
- [ ] 1.4 Remove hardcoded Facebook token from `gs-web-app/app/src/common/config.js` — replace with runtime env var or server-side proxy call
- [ ] 1.5 Verify no other hardcoded secrets remain in the gs-web-app bundle (scan: `grep -r "password\|token\|secret\|k2Zs" app/src/`)

## 2. gd-es-middleware — Write-Path Authentication

- [ ] 2.1 Instantiate `AuthManager` in `documents.controller.ts::updateDocument()` — call `authManager.validate()` before processing; return 401 if validation fails
- [ ] 2.2 Instantiate `AuthManager` in `documents.controller.ts::saveDocument()` — call `authManager.validate()` before processing; return 401 if validation fails
- [ ] 2.3 Implement field blocklist function — strip `depRole`, `_depIds`, `_superAdmin`, `_id` from `req.body` before passing to `elastic.updateDocument()` (bypass for SUPER_ADMIN callers)
- [ ] 2.4 Implement ownership check for `_dataSource: "user"` writes — assert `req.body._id === authManager.userDoc._id`; return 403 on mismatch
- [ ] 2.5 Write unit tests for 2.1–2.4: 401 on missing header, 401 on unknown user, 403 on ownership mismatch, field stripping for each blocked field, SUPER_ADMIN bypass
- [ ] 2.6 Integration test: confirm the original exploit path (`PATCH /documents` with `depRole: SUPER_ADMIN` as DEPARTMENT_HEAD) returns 401/403
- [ ] 2.7 Run `lsp_diagnostics` / TypeScript build on changed files — zero errors before merge

## 3. gs-mgt-server — bcrypt Password Storage

- [ ] 3.1 Add `bcrypt` npm package to `package.json`
- [ ] 3.2 Write one-time migration script (`scripts/migrate-passwords.js`) — for each user in MongoDB `users` collection with non-bcrypt password, hash with bcrypt (cost 12), update document; skip already-bcrypt records (`$2b$` prefix)
- [ ] 3.3 Test migration script against a dev DB backup — verify all accounts can log in after migration
- [ ] 3.4 Update `dataHandler.js::login()` — replace plaintext `find({password: req.body.password})` with: `find({username})` then `bcrypt.compare(req.body.password, user.password)` 
- [ ] 3.5 Write unit tests for the new login handler: correct password succeeds, incorrect password returns 401, bcrypt compare is called (not string equality)
- [ ] 3.6 Write unit tests for migration script: idempotency (already-bcrypt record untouched), plaintext record is migrated correctly
- [ ] 3.7 Schedule and run migration script in dev → staging → prod (maintenance window); verify all user logins work after each environment

## 4. DocServerV2 — Write-Path Authentication + OPA Dead Code Removal

- [ ] 4.1 Audit all internal callers of DocServerV2 write routes — confirm they pass `X-Cyber-Userinfo` header (or document which ones don't and need to be updated)
- [ ] 4.2 Implement `require_identity()` FastAPI dependency in DocServerV2 — decode `X-Cyber-Userinfo` header (base64 JSON); return HTTP 401 if absent or malformed
- [ ] 4.3 Inject `require_identity` dependency into `create_document` route handler
- [ ] 4.4 Inject `require_identity` dependency into `update_document` (PATCH) route handler
- [ ] 4.5 Inject `require_identity` dependency into `delete_document` route handler
- [ ] 4.6 Inject `require_identity` dependency into `_bulkInsert`, `_bulkDelete`, `_bulkUpdate` route handlers
- [ ] 4.7 Delete dead OPA code: `api/rego/opa.py`, `api/policies/policy.rego`, `api/policies/accesscontrol.rego`
- [ ] 4.8 Remove `AUTHORIZED_MODE` env var references from `config.py` and all route handlers
- [ ] 4.9 Write unit tests for `require_identity()`: 401 on missing header, 401 on malformed base64, 401 on non-JSON payload, successful decode of valid header
- [ ] 4.10 Integration test: confirm `PATCH /docs/{collection}/{id}` without `X-Cyber-Userinfo` returns 401
- [ ] 4.11 Run pytest on changed files — zero failures before merge

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

- [ ] 7.1 All unit tests pass (zero failures) for each service modified (2.5, 3.5, 3.6, 4.9, 5.4, 6.6)
- [ ] 7.2 Integration test confirms original P0 exploit path returns 401/403 on dev and staging
- [ ] 7.3 `lsp_diagnostics` / build clean on all modified TypeScript files (gd-es-middleware)
- [ ] 7.4 pytest clean on all modified Python files (DocServerV2, authserver)
- [ ] 7.5 Credential rotation verified in all environments before any code changes merge
- [ ] 7.6 PR review includes security checklist: no new plaintext secrets, no `as any` / type suppression, auth middleware verified on all listed routes
