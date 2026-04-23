## 1. Prepare Host Directories

- [x] 1.1 Create install directory `/home/riwut/workspace/archon/`
- [x] 1.2 Create data directory `/data/archon-data/`

## 2. Create Configuration Files

- [x] 2.1 Create `.env` with `PORT=5678`, `CLAUDE_USE_GLOBAL_AUTH=true`, `DEFAULT_AI_ASSISTANT=claude`, `ARCHON_DATA=/data/archon-data`
- [x] 2.2 Copy `docker-compose.yml` from Archon source (`opensrc/repos/github.com/coleam00/Archon/docker-compose.yml`) into `/home/riwut/workspace/archon/`
- [x] 2.3 Create `docker-compose.override.yml` that mounts `~/.claude:/home/appuser/.claude:ro`

## 3. Build and Start

- [x] 3.1 Run `docker compose up -d --build` in `/home/riwut/workspace/archon/` (first build takes 3-5 min)
- [x] 3.2 Verify container is running: `docker compose ps`
- [x] 3.3 Verify health endpoint returns HTTP 200: `curl http://localhost:5678/api/health`

## 4. Verify Installation

- [x] 4.1 Confirm web UI loads at `http://localhost:5678`
- [x] 4.2 Confirm data directory is created: `ls /data/archon-data/`
- [x] 4.3 Register a test codebase and confirm Claude is available as AI assistant
