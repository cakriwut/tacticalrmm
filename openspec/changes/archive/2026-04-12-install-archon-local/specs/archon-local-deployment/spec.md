## ADDED Requirements

### Requirement: Archon runs locally via Docker Compose on port 5678
The system SHALL provide a Docker Compose configuration that starts Archon on port 5678 on the local machine using SQLite as the default database.

#### Scenario: Service starts successfully
- **WHEN** `docker compose up -d` is run in `/home/riwut/workspace/archon/`
- **THEN** the Archon container starts and the health check at `http://localhost:5678/api/health` returns HTTP 200 within 30 seconds

#### Scenario: Web UI is accessible
- **WHEN** a browser navigates to `http://localhost:5678`
- **THEN** the Archon web UI loads successfully

### Requirement: Archon data persists on /data disk
The system SHALL store all Archon data (SQLite DB, workspaces, worktrees, artifacts) at `/data/archon-data` on the host, bound into the container at `/.archon`.

#### Scenario: Data survives container restart
- **WHEN** the Archon container is stopped and restarted with `docker compose up -d`
- **THEN** all previously registered codebases and workflow run history remain intact

#### Scenario: Data directory is on correct disk
- **WHEN** Archon writes data (registers a codebase, runs a workflow)
- **THEN** files appear under `/data/archon-data/` on the host

### Requirement: Claude auth uses explicit OAuth token
The system SHALL use `CLAUDE_CODE_OAUTH_TOKEN` set explicitly in `.env` with `CLAUDE_USE_GLOBAL_AUTH=false` to authenticate with Claude.

#### Scenario: Claude auth is active at startup
- **WHEN** the container starts with `CLAUDE_CODE_OAUTH_TOKEN` set and `CLAUDE_USE_GLOBAL_AUTH=false`
- **THEN** container logs show `authMode: "explicit"` and `using_explicit_tokens` with no auth errors

#### Scenario: Token refresh required
- **WHEN** the OAuth token expires (typically every few weeks)
- **THEN** the operator copies `$CLAUDE_CODE_OAUTH_TOKEN` from the host shell into `.env` and runs `docker compose up -d` to pick up the new token

### Requirement: Install directory contains all required configuration files
The system SHALL have a dedicated install directory at `/home/riwut/workspace/archon/` containing `.env`, `docker-compose.yml`, `docker-compose.override.yml`, and `.gitconfig`.

#### Scenario: All required files present
- **WHEN** the install directory is inspected
- **THEN** `.env`, `docker-compose.yml`, `docker-compose.override.yml`, and `.gitconfig` are all present

#### Scenario: .env has correct values
- **WHEN** `.env` is read
- **THEN** `PORT=5678`, `CLAUDE_USE_GLOBAL_AUTH=false`, `DEFAULT_AI_ASSISTANT=claude`, `ARCHON_DATA=/data/archon-data`, and `CLAUDE_CODE_OAUTH_TOKEN` are set

### Requirement: Container runs as host user uid=1000
The system SHALL run the Archon container with `user: "1000:1000"` so it has read/write access to all host workspace files without permission errors.

#### Scenario: Container uid matches host uid
- **WHEN** `docker exec archon-app-1 id` is run
- **THEN** output shows `uid=1000`

#### Scenario: Git worktree creation succeeds
- **WHEN** Archon runs a workflow that creates a git worktree in a local codebase
- **THEN** the worktree is created without `Permission denied` errors on `.git/refs/heads/`

### Requirement: Local codebases are accessible inside the container
The system SHALL mount `/home/riwut/workspace` into the container at the same path so local repos can be registered by their host path.

#### Scenario: Local codebase registration succeeds
- **WHEN** a path like `/home/riwut/workspace/flux-cyber` is registered in Archon
- **THEN** Archon can access the git repo without `No such file or directory` errors

### Requirement: Git credential store is available inside the container
The system SHALL mount `~/.git-credentials` read-only into `/home/bun/.git-credentials` and configure `credential.helper = store` in the container gitconfig so private remotes (e.g. Azure DevOps) can be fetched.

#### Scenario: Azure DevOps fetch succeeds
- **WHEN** Archon syncs a codebase with an Azure DevOps remote
- **THEN** `git fetch origin main` succeeds without password prompt errors

#### Scenario: Credential write warning is harmless
- **WHEN** git attempts to refresh credentials after a successful fetch
- **THEN** the warning `unable to write credential store: Device or resource busy` appears in logs but the fetch succeeds

### Requirement: Repos without remotes require a self-referential remote
The system SHALL require that all codebases registered in Archon have at least one git remote, because Archon always runs `git fetch origin <branch>` on sync.

#### Scenario: Self-referential remote enables sync
- **WHEN** a local repo with no remote is registered and `git remote add origin /home/riwut/workspace/<repo>` is run
- **THEN** Archon sync succeeds with `workspace.sync_completed`
