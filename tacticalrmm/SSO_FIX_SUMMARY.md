# Tactical RMM Microsoft Entra SSO Fix

## Summary

Fixed a critical issue where Microsoft Entra SSO login would succeed but immediately redirect to "Session Expired" (404 on `/account/provider/callback`).

**GitHub Branch**: [feature/sso-microsoft-entra-callback-fix](https://github.com/cakriwut/tacticalrmm/tree/feature/sso-microsoft-entra-callback-fix)

**Status**: ✅ Tested and deployed on Contabo 45.159.220.200

## Root Causes

### 1. Missing Frontend Route (404 → /expired)
- Official `tacticalrmm/tactical-frontend:latest` (Jan 2026) has no route for `/account/provider/callback`
- After Microsoft Entra redirects back to callback URL, nginx serves `index.html` (SPA)
- Vue router matches `/:catchAll(.*)` (NotFound component)
- First API call returns 401 (no valid token yet)
- axios 401 interceptor redirects to `/expired`

### 2. Token Serialization Bug (401 on All API Calls)
- `sso-callback.html` was storing: `localStorage.setItem('access_token', JSON.stringify(data.token))`
- This wraps the token in JSON quotes: `"a3794d38..."` (with quotes in the string)
- Vue auth store uses `useStorage("access_token", null)` with default `any` serializer
- `any` serializer's `read` function: `e => e` (passthrough, no JSON.parse)
- Result: `store.token = '"a3794d38..."'` (with quotes)
- axios header: `Authorization: Token "a3794d38..."` → **backend rejects with 401**

## Solution

### Files Added

#### 1. `00-sso-callback.conf` (nginx server block)
- Serves on `rmm.s2t.ai:4443`
- `location = /account/provider/callback` (exact match, highest priority)
- Serves `sso-callback.html` static page
- Sorts before `default.conf` alphabetically so this block wins in nginx

#### 2. `sso-callback.html` (Token exchange page)
- Standalone HTML/JavaScript page (no framework dependencies)
- Flow:
  1. Checks for `?error=` query param → shows error message
  2. On success: POSTs to `accounts/ssoproviders/token/` with session cookie
     - `credentials: 'include'` sends Django session cookie (set by allauth backend callback)
     - `X-CSRFToken` header for CSRF protection
  3. Backend returns Knox token
  4. **FIXED**: Stores raw token: `localStorage.setItem('access_token', data.token)` (no JSON.stringify)
  5. Also stores: `user_name`, `name`, `sso_provider` (raw strings)
  6. Redirects to `/` (or saved `next` route from localStorage)

#### 3. Updated `apply-changes.py` 
- **Step 5**: Write `00-sso-callback.conf` to `/opt/tactical/`
- **Step 6**: Write `sso-callback.html` to `/opt/tactical/` and Docker volume
- Updates docker-compose.yml with bind mounts for persistence

#### 4. Updated `docker-compose.yml`
```yaml
volumes:
  - /opt/tactical/00-sso-callback.conf:/etc/nginx/conf.d/00-sso-callback.conf:ro
  - /opt/tactical/sso-callback.html:/opt/tactical/sso-callback.html:ro
```

## Deployment

### Step 1: Pull Changes
```bash
cd ~/workspace/devops
git fetch github-rmm feature/sso-microsoft-entra-callback-fix
git checkout feature/sso-microsoft-entra-callback-fix
```

### Step 2: Deploy to Contabo
```bash
python3 tacticalrmm/apply-changes.py
```

This will:
1. Update `.env` with `AGENT_BASE_URL`
2. Write nginx configs (agents.conf, 00-sso-callback.conf)
3. Patch docker-compose.yml
4. Validate compose
5. Pull latest images
6. Restart containers with new mounts

### Step 3: Test
1. Navigate to `https://rmm.s2t.ai/login`
2. Click "Microsoft" (Entra) button
3. Authenticate with Microsoft
4. Should redirect to `/account/provider/callback` → token exchange → dashboard
5. Verify you're logged in and can access agents

## Testing Evidence

### Jam Reports
- **First issue** (404/expired): https://jam.dev/c/518e2acc-90e3-4df4-ad96-7e78222cfbaf
- **Second issue** (401 after redirect): https://jam.dev/c/f7003d7b-e911-4104-846d-7a28979eccd7

### Network Flow Verified
✅ POST `/accounts/oidc/Microsoft/login/callback/` → 200 (backend processes auth)
✅ GET `/account/provider/callback` → 200 (nginx serves callback page)
✅ POST `/accounts/ssoproviders/token/` → 200 (token exchange succeeds)
✅ REST API calls (alerts, dashinfo, etc.) → 200 (valid token accepted)

## Technical Details

### Why This Works
1. **Location = exact match** has highest priority in nginx
   - `location = /account/provider/callback` matches exactly and takes priority over other rules
   
2. **Frontend doesn't need modification**
   - Uses official `tacticalrmm/tactical-frontend:latest` image
   - No rebuild needed
   
3. **Token format matches Vue auth store expectations**
   - `any` serializer: `read: e => e` (raw string passthrough)
   - Store raw token without JSON wrapping
   
4. **Persistence through container recreation**
   - Bind mounts in docker-compose.yml
   - Files on host `/opt/tactical/` survive container restart
   - apply-changes.py ensures files are in place before deployment

### CORS & Security
- ✅ CORS configured: `access-control-allow-origin: https://rmm.s2t.ai`
- ✅ Credentials allowed: `access-control-allow-credentials: true`
- ✅ CSRF token validated
- ✅ Callback page only runs client-side (no server-side token storage)

## Files Changed

```
tacticalrmm/00-sso-callback.conf   (34 lines) - NEW
tacticalrmm/sso-callback.html      (109 lines) - NEW
tacticalrmm/apply-changes.py       (+199 lines) - Updated
tacticalrmm/docker-compose.yml     (mounted in apply-changes.py)
```

## Next Steps (Optional)

### To Make This Official
1. Submit PR to `cakriwut/tacticalrmm` from this branch
2. Merge to master once tested
3. Build & tag new Docker image version
4. Update deployment docs

### To Extend
- Add SSO callback route to Vue SPA frontend (clean solution, requires frontend rebuild)
- Support other OIDC providers (already supported by allauth backend)
- Add user provisioning on first SSO login (optional)

## Rollback

If needed, revert without the SSO files:
```bash
# Remove nginx conf and callback page
rm /opt/tactical/00-sso-callback.conf
rm /opt/tactical/sso-callback.html
rm /var/lib/docker/volumes/tactical_tactical_data/_data/sso-callback.html

# Restart nginx
docker compose up -d tactical-nginx
```

Users will then see the 404 on callback again (restore from backup if needed).

---

**Tested**: June 8, 2026 — Riwut Libinuko
**Deployed**: Contabo 45.159.220.200 (cakriwut/tactical:latest + tacticalrmm/tactical-frontend:latest)
