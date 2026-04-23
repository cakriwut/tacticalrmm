## Why

The CEO operates in three distinct modes — Support (general knowledge & triage), Developer (technical implementation), and Tester (validation) — each requiring different AI personas, toolsets, and workspaces. A single shared agent context creates cognitive noise and tool bloat. Three isolated Hermes Agent profiles, each with a dedicated Slack bot and live messaging gateway, allow clean context-switching without losing continuity between roles.

## What Changes

- Install Hermes Agent (NousResearch) on this machine via the official install script
- Create three isolated profiles: `support`, `developer`, `tester`
- Configure each profile with a role-specific SOUL.md persona, toolset scope, model, and workspace
- Set up three separate Slack apps (one per profile) in a single Slack workspace, each in its own channel
- Install each profile's gateway as a systemd boot-time service so all three run concurrently
- Create `~/workspace/support/` with a `handoffs/` subdirectory as the cross-profile communication channel
- Create a handoff convention: Support writes structured markdown findings → Developer reads and implements → Tester validates and writes results back

## Capabilities

### New Capabilities

- `hermes-installation`: Install Hermes Agent binary and run initial `hermes setup`
- `support-profile`: Support profile — zAI model, web+file toolsets, `~/workspace/support/` workspace, Slack App 1
- `developer-profile`: Developer profile — Anthropic Claude model, full toolsets, `~/workspace/` workspace, Slack App 2
- `tester-profile`: Tester profile — Ollama Cloud model, terminal+file+browser toolsets, `~/workspace/` workspace, Slack App 3
- `handoff-convention`: Shared handoff channel at `~/workspace/support/handoffs/` with structured markdown format
- `gateway-services`: Three concurrent systemd gateway services, one per profile, all boot-time

### Modified Capabilities

<!-- none — greenfield installation -->

## Impact

- **New system dependency**: Hermes Agent (Python 3.11, uv) installed at `~/.local/bin/hermes`
- **New directories**: `~/workspace/support/`, `~/workspace/support/handoffs/`, `~/.hermes/profiles/support/`, `~/.hermes/profiles/developer/`, `~/.hermes/profiles/tester/`
- **New systemd services**: Three `hermes-gateway-<hash>` user services
- **Secrets required**: `ANTHROPIC_API_KEY`, `ZAI_API_KEY` (zAI/GLM), `OLLAMA_API_KEY` (ollama.com), three Slack bot tokens (`xoxb-`), three Slack app-level tokens (`xapp-`)
- **No existing code modified** — this is a new installation alongside existing workspace tooling
