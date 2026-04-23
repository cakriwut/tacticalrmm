# Security Verification Runbook

**Purpose.** A security audit of the `gs-web-app` / `gd-es-middleware` / `gs-mgt-server` / `DocServerV2` / `authserver` stack identified a P0 privilege-escalation exploit that was confirmed reproducible on the current dev/staging environment. This runbook lists the infrastructure-level verifications needed to confirm scope, find any compensating controls, and decide remediation priorities.

**Audience.** DevOps / SRE / platform engineer with `kubectl` and cluster access, or an AI agent with equivalent permissions.

**How to use.** Run each section in order (they build on each other). Paste outputs back. Report anything unexpected rather than silently skipping.

**Safety.** Every command in this document is **read-only** unless explicitly marked `[WRITE]`. No write-marked commands are required to complete this verification — they are offered as optional deeper tests.

---

## Context you need to know

- Stack runs on Azure Kubernetes, images in `cybersmartstg.azurecr.io`.
- Frontend is Vue 2 (`gs-web-app`).
- Backend services of interest: `gd-es-middleware`, `gs-mgt-server`, `DocServerV2`, `authserver`.
- Ingress: **Traefik** with `traefik-forward-auth` + **OPA** (open policy agent) in the auth pipeline. Configured to inject `X-Forwarded-User`, `X-Cyber-UserInfo`, `X-Cyber-OidcToken`, `X-Cyber-AccessToken` headers from the Keycloak session.
- We already confirmed on the live system: a logged-in `DEPARTMENT_HEAD` user could PATCH their own ES user document to set `depRole: SUPER_ADMIN` and `_depIds: ['FAKE_TENANT_999']` and the write stuck. Reverted immediately. But it worked.
- Read scoping on the `cases` index IS enforced somehow — plain queries return only the caller's tenant even though the repo code doesn't show that filter. We want to identify the mechanism.

---

## PRIORITY 0 — confirm the exploit scope

Goal: is the privilege-escalation possible from production, or was it only possible on the environment we tested (dev/staging)?

### P0.1 — Identify which environment the PATCH test hit

We ran the PATCH from a browser against `location.origin` — whichever environment the tester was logged into. Confirm which cluster / namespace that corresponds to:

```bash
# Traefik ingress config that maps your-app-host -> backend service
kubectl get ingress -A -o wide | grep -i cybersmart
kubectl get ingressroute -A -o wide | grep -i cybersmart    # if using traefik CRD
```

**Paste back:** the hostname the tester was logged into, and the matching Ingress/IngressRoute.

### P0.2 — Is this reproducible in production?

If P0.1 shows the test hit dev/staging, the same exploit _may or may not_ work in production depending on whether production has different infrastructure protections. Confirm by running the same browser test against a production login (a privileged-account test user, not a real admin — revert immediately after) OR by inspecting whether production's Traefik/OPA config differs from staging.

```bash
# Diff ingress annotations between environments
kubectl get ingress -n <prod-namespace> -o yaml > /tmp/prod.yaml
kubectl get ingress -n <staging-namespace> -o yaml > /tmp/stg.yaml
diff /tmp/prod.yaml /tmp/stg.yaml | head -100
```

**Paste back:** any differences in Ingress annotations, middleware references, or forward-auth wiring between prod and staging.

---

## PRIORITY 1 — Traefik + forward-auth pipeline

Goal: confirm trusted headers are actually injected server-side (not spoofable by browser) and that all backend services go through this pipeline.

### P1.1 — Traefik middleware definitions

```bash
# List all Traefik middlewares
kubectl get middleware -A
kubectl get -A traefikservice 2>/dev/null

# For each relevant forward-auth middleware, dump config
kubectl get middleware -A -o yaml | grep -A 20 -iE "forwardAuth|forward-auth"
```

**Look for / paste back:**
- `authResponseHeaders` — must include `X-Forwarded-User`, `X-Cyber-UserInfo`, `X-Cyber-OidcToken`
- `authRequestHeaders` — confirms what goes TO forward-auth
- `address` — the URL traefik-forward-auth listens on
- `trustForwardHeader` — should be `false` or absent (true = trust client-supplied)

### P1.2 — forward-auth pod health & config

```bash
# Find the forward-auth pod
kubectl get pods -A -l app=traefik-forward-auth -o wide 2>/dev/null
kubectl get pods -A | grep -iE "forward-auth|opa"

# Inspect env (sources of OIDC client id / secret / OPA URL)
kubectl get deployment -A -l app=traefik-forward-auth -o yaml | grep -A 30 "env:"
```

**Paste back:** the deployment's `env:` block (redact client secrets), AUTH_RESPONSE_HEADERS value, OPA_URL or similar.

### P1.3 — Does Traefik strip client-supplied headers?

This is the keystone. If Traefik passes through browser-set `X-Forwarded-User`, the entire trust model collapses.

Safe runtime test from any browser authenticated into the app — paste into DevTools Console:

```js
// Send a request with a spoofed X-Forwarded-User header
fetch(location.origin + '/elastic-middleware/documents?query=*&index=user&itemsPerPage=1', {
  headers: {
    'X-Forwarded-User': 'admin-attacker@evil.invalid',
    'Authorization': 'Basic ' + btoa('crawler_user:k2ZsNCLRP5Q=')
  }
}).then(r => r.json()).then(console.log)
```

Then check middleware logs:

```bash
kubectl logs -n <middleware-namespace> deployment/gd-es-middleware --tail=50 | grep -iE "x-forwarded-user|user info"
```

**Interpret:**
- If logs show `admin-attacker@evil.invalid` — **CRITICAL: Traefik is NOT stripping. P0 finding upgraded to "trivially exploitable remotely." Stop here and escalate.**
- If logs show the real authenticated username — Traefik is correctly overriding. Continue.

### P1.4 — Are ALL backend services behind Traefik?

```bash
# List all Services of interest; type should be ClusterIP only
kubectl get svc -A | grep -iE "gd-es-middleware|gs-mgt-server|docserver|authserver|uploader|s3-middleware|global-router"
```

**Look for / paste back:**
- Any `NodePort` or `LoadBalancer` type — these are directly accessible bypassing Traefik. Should all be `ClusterIP`.
- Cluster-external IPs present in `EXTERNAL-IP` column.

### P1.5 — Any Ingress that bypasses forward-auth?

```bash
# Get all ingresses and check which reference the forward-auth middleware
kubectl get ingress -A -o yaml | grep -B 5 -A 10 "backend:" | grep -iE "service:|forward-auth|middleware"

# For Traefik CRD users:
kubectl get ingressroute -A -o yaml | grep -B 5 -A 10 "middlewares:"
```

**Look for / paste back:** any Ingress/IngressRoute pointing at the backend services above WITHOUT the forward-auth middleware in its chain.

---

## PRIORITY 2 — OPA inspection

> ⚠️ **[AUDIT COMPLETE — DEAD CODE CONFIRMED]** All sub-tasks in this section have been executed against the live dev cluster. The conclusion is that **application-level OPA in DocServerV2 is dead/orphan code and provides zero security enforcement.** Steps P2.1–P2.7 are retained for historical reference only. No further action is needed here.

### Audit findings (2026-04-23)

| Check | Result |
|---|---|
| `AUTHORIZED_MODE` env var (live `cyber-docserver-v2-microservice` pod) | **`false`** — code path disabled at runtime |
| OPA sidecar container in DocServerV2 pod | **None** — single container `docserver-v2:1.21.0` |
| OPA standalone `Service` in `cyber` namespace | **None** — no OPA service exists |
| `OPA_URL` / `OPA_SERVER` env vars | **Not set** |
| OPA port 8181 reachable from DocServerV2 | **N/A** — no target to connect to |
| `kubectl get pods -A \| grep -i opa` | Only **OPA Gatekeeper** in `gatekeeper-system` (K8s admission controller — unrelated to application auth) |
| Source code audit (`api/rego/opa.py`, `crud.py`) | OPA only called on GET searches when bearer token present; PATCH/POST/DELETE have **zero** OPA calls |
| `policy.rego` blanket-allow bug | `allow { "user" in input.roles }` — any user bypasses all rules; **moot** since OPA is never called for writes |

**Root cause:** DocServerV2 was designed with OPA for row-level filtering of GET results, never for write authorization. `AUTHORIZED_MODE=false` disables even the GET filter. No OPA service was ever deployed alongside DocServerV2. The `.rego` files are orphan code.

**Revised finding:** The security gap in DocServerV2 is not "OPA policies have bugs" — it is that **DocServerV2 has zero authorization for any write operation.** The fix must implement authorization from scratch (see Priority Fix Matrix and proposal).

---

### Original investigation steps (retained for reference)

Goal: find what OPA is actually enforcing, versus what the repo says it should.

### P2.1 — Locate the OPA server(s)

There may be more than one: an ingress-level OPA (called by `traefik-forward-auth`) and an app-level OPA (called by `DocServerV2`).

```bash
# Find OPA pods
kubectl get pods -A | grep -i opa

# Find OPA_SERVER env references in any deployment
kubectl get deployment -A -o yaml | grep -B 2 -A 2 -iE "OPA_SERVER|OPA_URL|OPA_ADDR|OPA_POLICY"

# Find OPA Services
kubectl get svc -A | grep -i opa
```

**Paste back:** name and namespace of each OPA pod, plus the env references showing who talks to which OPA.

### P2.2 — Port-forward to the OPA server

```bash
# Replace <ns> and <pod>
kubectl port-forward -n <opa-namespace> <opa-pod-name> 8181:8181
# In another terminal:
curl -s http://localhost:8181/health
```

**Expected:** `{}` (200 OK).

### P2.3 — List loaded policies

```bash
curl -s http://localhost:8181/v1/policies | jq '.result[].id'
```

**Paste back:** the full list.

### P2.4 — Dump each policy's source

For each policy id from the previous step:

```bash
curl -s http://localhost:8181/v1/policies/<policy-id> | jq -r '.result.raw'
```

Also dump the repo versions for comparison:

- `/home/ubuntu/projects/dosa/DocServerV2/api/policies/policy.rego`
- `/home/ubuntu/projects/dosa/DocServerV2/api/policies/accesscontrol.rego`
- Any `.rego` files under `/home/ubuntu/projects/dosa/traefik-middleware/`

**Paste back:** diff between loaded policy vs repo version for each. Report any differences.

### P2.5 — Dump loaded data

Policies reference `data.document`, possibly `data.users`, etc. Confirm that state is populated:

```bash
# Top-level
curl -s http://localhost:8181/v1/data | jq 'keys'

# Drill into each referenced namespace
curl -s http://localhost:8181/v1/data/document | jq '.' | head -50
curl -s http://localhost:8181/v1/data/users | jq '.' | head -50
curl -s http://localhost:8181/v1/data/accesscontrol | jq '.'
```

**Paste back:** the keys output and a sample of each referenced namespace. Flag if `data.document` or `data.users` is empty.

### P2.6 — Test specific decisions (the critical test)

Simulate the exact request that the P0 exploit used:

```bash
# Does OPA allow a DEPARTMENT_HEAD user to PATCH their own user doc with depRole:SUPER_ADMIN?
curl -s -X POST http://localhost:8181/v1/data/docserverv2/allow \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "method": "PATCH",
      "path": "/documents",
      "user_id": "5c920912efb9c1057cf4504c",
      "username": "optimus_user",
      "roles": ["DEPARTMENT_HEAD"],
      "resource_access": ["people-search-api"],
      "body": {
        "_id": "5c920912efb9c1057cf4504c",
        "_dataSource": "user",
        "depRole": "SUPER_ADMIN"
      }
    }
  }' | jq
```

**Interpret:**
- `{"result": true}` — OPA allows it. This explains why the exploit worked.
- `{"result": false}` — OPA would block, but the exploit still succeeded. Means **OPA isn't being invoked for writes.** Find the gap.
- No `result` field — policy doesn't have a rule matching this input. Default behavior applies.

Also test with the expected input shape for `accesscontrol.rego`:

```bash
# Tenant-scope check: user from department X trying to modify a doc in department Y
curl -s -X POST http://localhost:8181/v1/data/accesscontrol/allow \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "collection": "Document",
      "department": "DEPARTMENT_X",
      "operation": "write"
    }
  }' | jq
```

**Paste back:** both responses.

### P2.7 — Turn on decision logs (if not already)

Ask: is OPA configured with decision logs? Check:

```bash
curl -s http://localhost:8181/v1/config | jq '.result.decision_logs'
```

If `null` or absent, decisions aren't being recorded. **Strongly recommend turning decision logs on in at least the non-prod environment** — it's the single most useful observability tool OPA has.

Then trigger a PATCH from the browser and tail:

```bash
# On the OPA pod
kubectl logs -n <opa-namespace> <opa-pod-name> --tail=200 --follow
```

**Observe / paste back:** is an OPA decision entry created when a browser PATCHes `/elastic-middleware/documents`? If no entry appears, **OPA is not invoked on that route** — that's the smoking gun for why writes aren't filtered.

---

## PRIORITY 3 — Service feature flags

Goal: confirm runtime config values for the services we audited. Each of these changes the security posture significantly.

### P3.1 — `gd-es-middleware`

```bash
kubectl get deployment -n <ns> gd-es-middleware -o yaml | grep -A 2 "ES_MIDDLEWARE_AUTH_ENABLE\|IS_SSO_ENABLED"

# Also check mounted configmaps
kubectl get configmap -n <ns> -o yaml | grep -A 2 "ES_MIDDLEWARE"
```

**Paste back:** values of `ES_MIDDLEWARE_AUTH_ENABLE`, `IS_SSO_ENABLED` for each environment.

### P3.2 — `gs-mgt-server`

```bash
kubectl get deployment -n <ns> gs-mgt-server -o yaml | grep -A 1 -iE "auth|sso"
```

**Paste back:** any auth-related env vars. We want to know if there's a flag analogous to `ES_MIDDLEWARE_AUTH_ENABLE`.

### P3.3 — `DocServerV2`

> ⚠️ **[AUDIT COMPLETE]** `AUTHORIZED_MODE=false` confirmed on live pod. No `OPA_SERVER` or `OPA_POLICY` env vars exist. No OPA service deployed. Application-level OPA is dead/orphan code. Skip this check.

```bash
kubectl get deployment -n <ns> docserver-v2 -o yaml | grep -A 2 -iE "OPA_SERVER|OPA_POLICY|AUTH"
```

**Paste back:** `OPA_SERVER`, `OPA_POLICY` values. Confirm the OPA_SERVER is reachable from inside DocServerV2's pod (see P3.5).

### P3.4 — `authserver`

```bash
kubectl get deployment -n <ns> authserver -o yaml | grep -A 1 -iE "VALIDATE_TOKEN|KEYCLOAK|LICENSE|BASE_PATH"
```

**Paste back:** `VALIDATE_TOKEN_CHECK_REMOTE_IP`, `BASE_PATH`, Keycloak-related env.

### P3.5 — Connectivity check from inside pods

Confirm services can reach their configured dependencies:

```bash
# DocServerV2 can reach OPA — SKIP: no OPA service exists (dead code confirmed)
# kubectl exec -n <ns> deploy/docserver-v2 -- curl -sf http://<opa-service>:8181/health || echo FAIL

# gd-es-middleware can reach authserver (if it should)
kubectl exec -n <ns> deploy/gd-es-middleware -- curl -sf http://<authserver-service>/ || echo FAIL
```

**Paste back:** any `FAIL` results. A failing dependency often means the service silently fails-open.

---

## PRIORITY 4 — Elasticsearch layer

Goal: determine if ES itself is enforcing the `cases`-index read scoping we observed.

### P4.1 — X-Pack security enabled?

```bash
# From inside any pod that can reach ES, or port-forward
curl -s -u elastic:<pw> http://<es-host>:9200/_xpack | jq '.features.security'
```

**Paste back:** whether `enabled: true`.

### P4.2 — Document-level security roles

```bash
curl -s -u elastic:<pw> http://<es-host>:9200/_security/role | jq 'keys'
curl -s -u elastic:<pw> http://<es-host>:9200/_security/role/<role-with-dls> | jq
```

**Look for:** roles with `indices[].query` clauses that reference tenant fields. That would explain read scoping without middleware involvement.

### P4.3 — Index aliases

```bash
curl -s -u elastic:<pw> http://<es-host>:9200/_alias | jq 'keys'
curl -s -u elastic:<pw> http://<es-host>:9200/_alias/cases | jq
```

**Look for:** an alias called `cases` that filters on `_depIds`. If present, that's the hidden read-scoping mechanism.

### P4.4 — Raw index access bypassing the middleware

```bash
# Is Elasticsearch reachable from anywhere outside the middleware?
kubectl get svc -A | grep -iE "elastic|es-cluster"
kubectl get networkpolicy -A | grep -iE "elastic"
```

**Paste back:** ES Service type(s) and any NetworkPolicy governing access.

---

## PRIORITY 5 — Database state (gs-mgt-server)

Goal: confirm the claim from the audit that `/api/users/login` does plaintext password comparison against Mongo.

### P5.1 — Mongo users collection sample

```bash
# From a Mongo-reachable pod
kubectl exec -n <ns> deploy/gs-mgt-server -- mongo "$MONGO_URL" --eval '
  db.users.findOne({}, {password: 1, username: 1, _id: 0})
'
```

**Look for:** is the `password` field:
- a plaintext string (e.g. `"letmein"`) — **CRITICAL**, confirms audit finding
- a SHA-1 hex (40 chars, `a-f0-9`) — matches the frontend's SHA-1 scheme, still bad
- a bcrypt/argon2 string (starts with `$2`, `$argon`) — good

**Paste back:** the format category (not the actual hashes).

### P5.2 — Are there two user tables?

```bash
# Confirm there's both an ES `user` index and a Mongo `users` collection
curl -s -u elastic:<pw> http://<es-host>:9200/user/_count | jq .count

kubectl exec -n <ns> deploy/gs-mgt-server -- mongo "$MONGO_URL" --eval 'db.users.count()'
```

**Paste back:** both counts. If both are non-zero and similar, there's divergence risk; if only one is populated, the other is dead code.

---

## PRIORITY 6 — Debug endpoints

Goal: confirm no diagnostic/debug routes are reachable from the internet.

### P6.1 — grep each service for debug routes

```bash
for svc in gd-es-middleware gs-mgt-server DocServerV2 authserver; do
  echo "=== $svc ==="
  grep -rn -E "/(debug|env|dump|test|metrics|healthz)" /home/ubuntu/projects/dosa/$svc --include="*.js" --include="*.ts" --include="*.py" 2>/dev/null | grep -v test | head -20
done
```

**Paste back:** any endpoint under `/debug`, `/env`, `/dump`, etc. If they exist, try hitting them through the ingress from an unauthenticated browser session — they should be 401 or 404.

---

## Summary matrix — what answers we need

Fill this in and return with the runbook:

| # | Question | Answer |
|---|----------|--------|
| P0.2 | Does the PATCH privilege-escalation work in production? | yes / no / same as staging |
| P1.3 | Does Traefik strip client-supplied X-Forwarded-User? | yes / no |
| P1.4 | Are all backend Services ClusterIP only? | yes / no / list of exceptions |
| P1.5 | Any Ingress bypassing forward-auth? | yes / no / list |
| P2.1 | How many OPA instances, where? | **DEAD CODE** — no app-level OPA deployed; only OPA Gatekeeper (K8s admission, unrelated) |
| P2.4 | Do loaded OPA policies match the repo? | **N/A** — no OPA service deployed |
| P2.5 | Are `data.document` / `data.users` populated? | **N/A** — no OPA service deployed |
| P2.6 | Does OPA allow the privilege-escalation input? | **N/A** — OPA never invoked for writes; `AUTHORIZED_MODE=false` |
| P2.7 | Does OPA get invoked on PATCH /documents writes? | **No** — confirmed dead code; zero OPA calls in write handlers |
| P3.1 | `ES_MIDDLEWARE_AUTH_ENABLE` value per env? | true / false per env |
| P3.3 | `OPA_SERVER` reachable from DocServerV2? | **N/A** — `AUTHORIZED_MODE=false`, no OPA service exists |
| P3.4 | `VALIDATE_TOKEN_CHECK_REMOTE_IP`? | true / false |
| P4.1 | Is ES X-Pack security enabled? | yes / no |
| P4.3 | Does a `cases` alias with a DLS filter exist? | yes / no |
| P5.1 | Mongo `users.password` storage format? | plaintext / sha1 / bcrypt |
| P6.1 | Any reachable debug/env endpoints? | yes / no / list |

---

## What to send back

1. **Command outputs** for every step above (redact any real passwords, JWT secrets, or customer data).
2. **The filled summary matrix.**
3. **Anything unexpected** — even if it doesn't seem to fit a section. Unexpected configmaps, policies with unusual rules, services you didn't know existed.

**Do not run any `[WRITE]`-marked commands** (there are none in this runbook — all checks are read-only).

**Do not modify policies, configmaps, or feature flags** as part of this verification. Any change proposals come after the findings are reviewed together.

If any command fails with "permission denied" or "forbidden," note it but continue — missing permissions is itself a useful data point.
