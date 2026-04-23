## Context

The CEO uses a single Linux machine (`/home/riwut`) for all work. He operates across three distinct modes daily — Support (triage, general knowledge, log reading), Developer (code, infra, technical fixes), and Tester (validation, QA). Currently there is no agent setup; this is a greenfield installation.

Hermes Agent (NousResearch) is chosen because it natively supports:
- **Profile isolation** via `hermes profile create` — each profile gets its own `HERMES_HOME` subdirectory with independent config, SOUL.md, memory, sessions, and gateway
- **Concurrent live gateways** — each profile runs its own `hermes-gateway-<hash>` systemd service; all three can be active simultaneously without port or PID conflicts
- **Per-profile Slack bots** — each profile connects to a different Slack app (bot token + app-level Socket Mode token) in the same workspace

The repo is already cloned at `/home/riwut/workspace/devops/hermes-agent/`.

## Goals / Non-Goals

**Goals:**
- Install Hermes Agent once; create 3 isolated profiles (`support`, `developer`, `tester`)
- Each profile has a distinct SOUL.md persona, model provider, toolset scope, and working directory
- All 3 gateways run concurrently as systemd boot-time services, reachable via separate Slack bots
- Support and Developer are connected by a markdown handoff convention at `~/workspace/support/handoffs/`
- All secrets stored in per-profile `.env` files (not committed); sourced via `hermes config set`

**Non-Goals:**
- Multi-user access (single CEO user only)
- Docker-based deployment (native install, systemd sufficient)
- Voice mode, TTS/STT
- Shared memory or cross-profile session history
- Custom skill development (use built-in skills + Skills Hub only for now)

## Decisions

### D1: Native profiles over separate `HERMES_HOME` env vars
**Decision**: Use `hermes profile create` (native profiles at `~/.hermes/profiles/<name>/`) rather than manually setting `HERMES_HOME=~/.hermes-<name>` per invocation.

**Rationale**: Native profiles auto-generate shell aliases (`support`, `developer`, `tester`), handle gateway service naming per-profile, and are the intended multi-identity path. Manual `HERMES_HOME` switching works but loses the alias and profile management benefits.

**Alternative considered**: Separate full `HERMES_HOME` dirs (e.g. `~/.hermes-support/`). Rejected — more maintenance overhead, no profile list/export/import support.

---

### D2: Three separate Slack apps, same workspace, different channels
**Decision**: Create 3 Slack apps at api.slack.com, each installed to the same workspace, each invited to its own channel (`#support`, `#developer`, `#tester`).

**Rationale**: Each Hermes profile needs its own `SLACK_BOT_TOKEN` (`xoxb-`) + `SLACK_APP_TOKEN` (`xapp-`). Socket Mode connections are per-app, not per-workspace — a single app token cannot serve multiple distinct bot identities. Three separate apps gives clean identity separation: the CEO knows which persona he is talking to by which channel he opens.

**Alternative considered**: One Slack app with multiple bot tokens via comma-separated `SLACK_BOT_TOKEN`. Rejected — this is for multi-workspace (same bot, different workspaces), not multi-identity (different bots, same workspace).

---

### D3: Model per profile — zAI for Support, Anthropic for Developer, Ollama for Tester
**Decision**:
- Support → `z.ai` GLM (`ZAI_API_KEY`, `GLM_BASE_URL=https://api.z.ai/api/paas/v4`) — fast, cost-effective for general knowledge Q&A and log reading
- Developer → Anthropic Claude Sonnet (`ANTHROPIC_API_KEY`) — strongest code reasoning for technical problem-solving
- Tester → Ollama Cloud (`OPENAI_API_KEY` + `OPENAI_BASE_URL=https://ollama.com/v1`) — capable, lower cost for QA validation tasks

**Rationale**: Matching model strength to task complexity minimizes cost while keeping Developer (the highest-value hat) on the best available model.

---

### D4: Handoff via markdown files in `~/workspace/support/handoffs/`
**Decision**: Support writes structured `.md` files to `~/workspace/support/handoffs/`. Developer reads them by checking the directory at session start or on request. Tester writes validation results back with a `validated-` prefix.

**Rationale**: Simple, visible, version-controllable. No inter-process communication needed. SOUL.md for each profile instructs the agent on the convention. The directory is shared across profiles (all have read/write access to `~/workspace/`).

**File naming**: `YYYYMMDD-<topic-slug>.md` for Support handoffs; `validated-YYYYMMDD-<topic-slug>.md` for Tester results.

---

### D5: Toolset scoping per profile
**Decision**:
- Support: `web,file` — no terminal execution (read-only investigation)
- Developer: `terminal,file,web,code,skills` — full power
- Tester: `terminal,file,browser` — run tests, validate UI, read results

**Rationale**: Limiting Support to non-destructive tools prevents accidental infra changes when in triage mode. Developer needs full access. Tester needs terminal (run test suites) and browser (UI validation) but not the full skills system.

---

### D6: Workspace paths in SOUL.md via `TERMINAL_CWD`
**Decision**: Set `TERMINAL_CWD` in each profile's `.env` to pin the working directory. Also instruct each SOUL.md to reinforce the workspace context.

- Support: `TERMINAL_CWD=~/workspace/support`
- Developer: `TERMINAL_CWD=~/workspace`
- Tester: `TERMINAL_CWD=~/workspace`

**Rationale**: `TERMINAL_CWD` in `.env` sets the gateway session working directory. Since each profile has its own `.env`, this is cleanly isolated without shell alias tricks.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Three concurrent gateways consuming memory | Each gateway is lightweight (~50-100MB idle); acceptable on a modern dev machine. Monitor with `hermes -p <name> gateway status` |
| Slack app tokens expire or need rotation | Tokens stored in per-profile `.env` — rotate via `hermes -p <name> config set SLACK_BOT_TOKEN xoxb-new-token`. Document rotation cadence |
| Support reads a sensitive log file and leaks info via Slack | Support is single-user (CEO only) + `SLACK_ALLOWED_USERS` set to CEO's Slack Member ID only. Low risk |
| Handoff files accumulate and become stale | Convention: archive handled handoffs to `~/workspace/support/handoffs/archive/` after Developer confirms fix |
| Ollama Cloud rate limits or availability | Tester is non-critical path; if Ollama is down, temporarily switch with `hermes -p tester config set model anthropic/claude-haiku-4` |
| `hermes profile create` stores profiles under `~/.hermes/profiles/` — not in this devops workspace | Profiles are user-level config (correct). Secrets stay in `~/.hermes/profiles/<name>/.env` (not committed). SOUL.md and config.yaml CAN be version-controlled by copying into this repo as templates |

## Migration Plan

1. Install Hermes Agent via official install script
2. Run `hermes setup` (base config, API key)
3. Create 3 profiles: `support`, `developer`, `tester`
4. Configure each profile: SOUL.md, config.yaml (model + toolsets + workspace), .env (API keys + Slack tokens)
5. Create `~/workspace/support/handoffs/` directory structure
6. Create 3 Slack apps at api.slack.com, install to workspace, obtain tokens
7. Configure Slack tokens in each profile's `.env`
8. Install all 3 gateways as system services: `sudo hermes -p <name> gateway install --system`
9. Start all 3: `sudo hermes -p <name> gateway start --system`
10. Enable boot linger: `sudo loginctl enable-linger $USER`
11. Verify: send a message to each Slack bot, confirm response

**Rollback**: `hermes -p <name> gateway stop` + `hermes profile delete <name>`. No existing tooling is modified.

## Open Questions

- Should SOUL.md files for each profile be committed to this devops repo as templates for reproducibility? (Recommended: yes, under `config/hermes-profiles/`)
- What Slack workspace is being used — existing company workspace or a new personal workspace?
- Should the `handoffs/` directory be git-tracked (useful for history) or gitignored (simpler)?
