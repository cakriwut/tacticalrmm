## Why

Archon is a self-hosted remote agentic coding platform that runs AI coding agents (Claude, Codex) against registered codebases via workflows. Installing it locally enables autonomous coding automation on this machine without relying on external hosted services.

## What Changes

- New Docker Compose setup at `/home/riwut/workspace/archon/` running Archon on port 5678
- New data directory at `/data/archon-data` on the `/data` disk (566GB available)
- Claude global auth mounted from host `~/.claude` into the container
- SQLite as the default database (zero config, suitable for solo use)
- No reverse proxy / no HTTPS — local access only

## Capabilities

### New Capabilities

- `archon-local-deployment`: Docker Compose configuration files and `.env` to run Archon locally on port 5678 with Claude auth and persistent data on `/data`

### Modified Capabilities

<!-- None — this is a new standalone deployment, no existing specs affected -->

## Impact

- Creates `/home/riwut/workspace/archon/` directory with compose files
- Creates `/data/archon-data/` for persistent Archon data (SQLite DB, workspaces, artifacts)
- Exposes port `5678` on localhost
- Requires Docker daemon running
- Depends on Claude CLI being authenticated (`~/.claude` credentials present)
- No impact on existing running services
