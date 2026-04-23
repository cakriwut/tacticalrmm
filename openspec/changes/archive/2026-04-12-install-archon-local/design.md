## Context

Archon is a self-hosted agentic coding platform (Bun/TypeScript) that orchestrates Claude/Codex agents against codebases. It ships as a Docker image with a React web UI and a REST/SSE API server. Source code is at `/home/riwut/workspace/devops/opensrc/repos/github.com/coleam00/Archon/`.

Container internals: multi-stage Bun build, app runs as `appuser` (uid=1001) by default, but overridden to run as host uid=1000 (`bun` in the image) to avoid file permission conflicts. HOME inside container when uid=1000 is `/home/bun`.

Data disk: `/dev/nvme0n1p7` (609GB) mounted at `/data` — Archon data stored at `/data/archon-data/`.

## Goals / Non-Goals

**Goals:**
- Run Archon locally on port 5678 via Docker Compose
- Use SQLite (zero-config, suitable for solo use)
- Run container as uid=1000 (host user) to avoid permission conflicts
- Store all Archon data on `/data/archon-data` (the large disk)
- Mount full workspace for local codebase access
- Minimal config — only what's required for local use

**Non-Goals:**
- HTTPS / TLS / Caddy reverse proxy (local access only)
- PostgreSQL (not needed for solo, low-concurrency use)
- Platform integrations (Telegram, Slack, Discord, GitHub webhooks)
- Authentication / login page on the web UI (trusted local network)

## Decisions

### Decision 1: Docker Compose build from source vs pre-built image
**Chosen**: Build from source (`docker compose up -d --build` using the repo's `Dockerfile`)
**Rationale**: Building from the local opensrc clone gives exact version control and avoids unknown image tags.
**Alternative**: Use `deploy/docker-compose.yml` (pre-built GHCR image) — simpler but less control.

### Decision 2: Install directory layout
**Chosen**:
- Compose files + config: `/home/riwut/workspace/archon/`
- Data volume: `/data/archon-data/` (on the large disk)
**Rationale**: Separates config (small, version-control friendly) from bulk data (workspaces, artifacts, SQLite DB).

### Decision 3: Claude auth via explicit CLAUDE_CODE_OAUTH_TOKEN
**Chosen**: `CLAUDE_USE_GLOBAL_AUTH=false` + `CLAUDE_CODE_OAUTH_TOKEN` in `.env`
**Rationale**: `CLAUDE_USE_GLOBAL_AUTH=true` reads from `~/.claude/.credentials.json` but the OAuth access token in that file is expired and the host CLI never writes the refreshed token back to disk (keeps it in memory only). The live token is available in the host shell as `$CLAUDE_CODE_OAUTH_TOKEN`.
**Alternative rejected**: `CLAUDE_USE_GLOBAL_AUTH=true` — fails because token on disk is always expired.
**Refresh procedure**: `echo "CLAUDE_CODE_OAUTH_TOKEN=$CLAUDE_CODE_OAUTH_TOKEN" >> .env && docker compose up -d` (run from host shell where the live token is available). Token expires approximately every few weeks.
**Permanent alternative**: Replace with `CLAUDE_API_KEY=sk-ant-api03-...` from https://console.anthropic.com/settings/keys.

### Decision 4: Run container as uid=1000
**Chosen**: `user: "1000:1000"` in `docker-compose.override.yml`
**Rationale**: Host workspace files are owned by `riwut` (uid=1000). Default Archon container user `appuser` is uid=1001. Running as uid=1001 causes `Permission denied` on every git operation touching workspace `.git/` directories. Running as uid=1000 eliminates all ACL workarounds.
**Critical**: HOME for uid=1000 inside the container is `/home/bun` (not `/home/appuser`). All volume mounts for credentials/config must target `/home/bun/`.
**DB prerequisite**: Before switching to uid=1000, run `sudo chown -R 1000:1000 /data/archon-data/` — otherwise SQLite is owned by uid=1001 and becomes read-only.

### Decision 5: Mount full workspace at same path
**Chosen**: `- /home/riwut/workspace:/home/riwut/workspace:rw`
**Rationale**: Archon requires the path registered as a codebase to be accessible inside the container. Mounting at the same path means host paths work as-is in the UI.

### Decision 6: Port 5678
**Chosen**: `PORT=5678` to avoid collision with common dev ports (3000, 8080).

## Risks / Trade-offs

- **Claude token expiry** → `CLAUDE_CODE_OAUTH_TOKEN` expires every few weeks. Must be manually refreshed from host shell. Mitigation: switch to `CLAUDE_API_KEY` for a permanent solution.
- **SQLite write serialization** → Fine for solo use. For 20+ concurrent workflows, migrate to PostgreSQL via `DATABASE_URL` + `--profile with-db`.
- **Source build time** → First `docker compose up --build` takes 3-5 minutes. Subsequent starts are instant (image cached).
- **Data on /data disk** → If `/data` is unmounted, Archon won't start. Acceptable for local dev.
- **Credential store read-only** → `~/.git-credentials` mounted `:ro` causes `unable to write credential store: Device or resource busy` warning on every git fetch. Harmless — reads succeed.

## Final Configuration

### `/home/riwut/workspace/archon/docker-compose.override.yml`
```yaml
services:
  app:
    build:
      context: /home/riwut/workspace/devops/opensrc/repos/github.com/coleam00/Archon
      dockerfile: Dockerfile
    user: "1000:1000"
    volumes:
      - ${HOME}/.claude:/home/bun/.claude
      - ${HOME}/.claude.json:/home/bun/.claude.json:ro
      - /home/riwut/workspace:/home/riwut/workspace:rw
      - /home/riwut/workspace/archon/.gitconfig:/home/bun/.gitconfig:ro
      - ${HOME}/.git-credentials:/home/bun/.git-credentials:ro
```

### `/home/riwut/workspace/archon/.env`
```
PORT=5678
CLAUDE_USE_GLOBAL_AUTH=false
DEFAULT_AI_ASSISTANT=claude
ARCHON_DATA=/data/archon-data
MAX_CONCURRENT_CONVERSATIONS=10
CLAUDE_CODE_OAUTH_TOKEN=<token from $CLAUDE_CODE_OAUTH_TOKEN on host>
```

### `/home/riwut/workspace/archon/.gitconfig`
```
[safe]
    directory = *
[user]
    name = Riwut Libinuko
    email = riwut.libinuko@s2t.ai
[init]
    defaultBranch = main
[credential]
    helper = store
```

## Gotchas Reference

### 1. OAuth token is always expired on disk
The host `claude` CLI refreshes its OAuth token in memory but **never writes it back to disk**. `~/.claude/.credentials.json` always has an expired token. `CLAUDE_USE_GLOBAL_AUTH=true` will always fail. Use `CLAUDE_CODE_OAUTH_TOKEN=$CLAUDE_CODE_OAUTH_TOKEN` (read from host shell env) instead.

### 2. HOME mismatch when running as uid=1000
When `user: "1000:1000"` is set, the container uid=1000 maps to the user `bun` (the Bun base image user), whose HOME is `/home/bun`. If mounts target `/home/appuser/`, they are inaccessible. Always mount to `/home/bun/`.

### 3. SQLite owned by wrong uid after user change
If the container previously ran as uid=1001 (`appuser`), `/data/archon-data/` is owned by 1001. Switching to uid=1000 makes SQLite read-only. Fix before restart:
```bash
sudo chown -R 1000:1000 /data/archon-data/
```

### 4. .git/ dirs owned by old uid
If any git operations were run inside the container as uid=1001, subdirectories like `.git/refs/heads/archon/` get created owned by 1001. Workflow worktree creation then fails with `Permission denied`. Fix:
```bash
sudo find /home/riwut/workspace -name ".git" -type d -exec sudo chown -R 1000:1000 {} +
```

### 5. git safe.directory required
Container git refuses to operate on repos owned by a different uid. `.gitconfig` must include:
```
[safe]
    directory = *
```

### 6. Archon always fetches from origin
`syncWorkspace()` always runs `git fetch origin <branch>` before any AI operation. Repos with no remote will fail sync. For local repos:
```bash
git remote add origin /home/riwut/workspace/<repo>
```
This creates a self-referential remote that satisfies the fetch requirement.

### 7. Codebase names from Azure DevOps URLs
Azure DevOps remote URLs contain `/_git/repo`. Archon parses the last two URL path segments, producing names like `_git/flux-cyber`. Rename via SQLite directly (no API for name updates):
```bash
docker exec archon-app-1 bun -e "
import {Database} from 'bun:sqlite';
const db = new Database('/.archon/archon.db');
db.run(\"UPDATE remote_agent_codebases SET name='org/repo' WHERE id='<id>'\");
db.close();
"
```

### 8. PATCH /api/codebases/{id} cannot rename
The API only exposes `allowEnvKeys` on `PATCH`. Codebase name, path, and URL can only be changed directly in SQLite (`remote_agent_codebases` table).

### 9. Docker compose restart vs up -d
`docker compose restart` does NOT reload `.env` or compose file changes. Always use `docker compose up -d` to apply configuration changes. It recreates the container only if configuration changed.

### 10. First build takes 3-5 minutes
The multi-stage Dockerfile installs Chromium and all system packages. Subsequent starts are instant from cache.

## Migration Plan

1. Create `/home/riwut/workspace/archon/` and `/data/archon-data/`
2. Copy `docker-compose.yml` from Archon source
3. Create `.env`, `docker-compose.override.yml`, `.gitconfig` as above
4. `sudo chown -R 1000:1000 /data/archon-data/`
5. `docker compose up -d --build` (first build ~3-5 min)
6. Verify: `curl http://localhost:5678/api/health`

**Rollback**: `docker compose down`

## Open Questions

- None.
