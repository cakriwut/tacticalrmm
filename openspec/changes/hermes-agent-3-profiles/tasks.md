## 1. Prerequisites & Installation

- [x] 1.1 Verify Python 3.11 is available (`python3.11 --version`); install via `pyenv` or system package manager if missing
- [x] 1.2 Install `uv` package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc`
- [x] 1.3 Install Hermes Agent: `curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash && source ~/.bashrc`
- [x] 1.4 Verify installation: `hermes --version` returns successfully
- [x] 1.5 Run base setup wizard: `hermes setup` (configure default model/provider; can use any key for now)

## 2. Slack App Creation (do this in browser before configuring profiles)

- [ ] 2.1 Create Slack App 1 ("Hermes Support") at https://api.slack.com/apps — add all required scopes (`chat:write`, `app_mentions:read`, `channels:history`, `groups:history`, `im:history`, `im:read`, `im:write`, `users:read`, `files:write`), enable Socket Mode, install to workspace — save `xoxb-` bot token and `xapp-` app token
- [ ] 2.2 Create Slack App 2 ("Hermes Developer") — same scopes + Socket Mode setup — save `xoxb-` and `xapp-` tokens
- [ ] 2.3 Create Slack App 3 ("Hermes Tester") — same scopes + Socket Mode setup — save `xoxb-` and `xapp-` tokens
- [ ] 2.4 Create Slack channels `#support`, `#developer`, `#tester` in the workspace (if not already existing)
- [ ] 2.5 Invite each bot to its respective channel (`/invite @HermesSupport` in `#support`, etc.)
- [ ] 2.6 Find CEO's Slack Member ID (Profile → Copy Member ID) — needed for `SLACK_ALLOWED_USERS` in all three profiles

## 3. Workspace Directory Structure

- [x] 3.1 Create support workspace: `mkdir -p ~/workspace/support/handoffs/archive`
- [x] 3.2 Verify Developer and Tester workspace exists: `ls ~/workspace` (already present)

## 4. Support Profile Setup

- [x] 4.1 Create profile: `hermes profile create support`
- [x] 4.2 Write SOUL.md for Support: edit `~/.hermes/profiles/support/SOUL.md` with the persona (patient first-responder, read-only tools, handoff convention at `~/workspace/support/handoffs/YYYYMMDD-<topic>.md`, five-section handoff format: Issue Summary / Evidence / Root Cause / Recommended Fix / Files Affected)
- [x] 4.3 Set Support model to zAI: `hermes -p support config set model glm-4-plus` (or appropriate GLM model name)
- [x] 4.4 Set Support API keys: `hermes -p support config set ZAI_API_KEY <your-zai-key>` and `hermes -p support config set GLM_BASE_URL https://api.z.ai/api/paas/v4`
- [x] 4.5 Set Support toolsets: `hermes -p support config set toolsets web,file`
- [x] 4.6 Set Support workspace: `hermes -p support config set TERMINAL_CWD ~/workspace/support`
- [x] 4.7 Set Support Slack tokens: `hermes -p support config set SLACK_BOT_TOKEN xoxb-<app1-token>` and `hermes -p support config set SLACK_APP_TOKEN xapp-<app1-token>`
- [x] 4.8 Set Support allowed users: `hermes -p support config set SLACK_ALLOWED_USERS <CEO-slack-member-id>`
- [x] 4.9 Verify Support config: `hermes -p support config` — confirm model, toolsets, workspace, Slack tokens all present

## 5. Developer Profile Setup

- [x] 5.1 Create profile: `hermes profile create developer`
- [x] 5.2 Write SOUL.md for Developer: edit `~/.hermes/profiles/developer/SOUL.md` with the persona (senior engineer, full tool access, check `~/workspace/support/handoffs/` for pending handoffs at session start, implement fixes, confirm completion)
- [x] 5.3 Set Developer model to Anthropic: `hermes -p developer config set model anthropic/claude-sonnet-4-5`
- [x] 5.4 No ANTHROPIC_API_KEY needed — Hermes auto-detects Claude Code OAuth credentials from `~/.claude/` (auto-refreshes). Optionally force provider: `hermes -p developer config set HERMES_INFERENCE_PROVIDER anthropic`
- [x] 5.5 Set Developer toolsets: `hermes -p developer config set toolsets terminal,file,web,code,skills`
- [x] 5.6 Set Developer workspace: `hermes -p developer config set TERMINAL_CWD ~/workspace`
- [x] 5.7 Set Developer Slack tokens: `hermes -p developer config set SLACK_BOT_TOKEN xoxb-<app2-token>` and `hermes -p developer config set SLACK_APP_TOKEN xapp-<app2-token>`
- [x] 5.8 Set Developer allowed users: `hermes -p developer config set SLACK_ALLOWED_USERS <CEO-slack-member-id>`
- [x] 5.9 Verify Developer config: `hermes -p developer config` — confirm all values

## 6. Tester Profile Setup

- [x] 6.1 Create profile: `hermes profile create tester`
- [x] 6.2 Write SOUL.md for Tester: edit `~/.hermes/profiles/tester/SOUL.md` with the persona (QA engineer, validates Developer output, reads handoff files from `~/workspace/support/handoffs/`, writes results to `validated-YYYYMMDD-<topic>.md`, five-section validation format: Validation Status / What Was Tested / Results / Edge Cases Found / Notes)
- [x] 6.3 Set Tester model to Ollama Cloud: `hermes -p tester config set model <ollama-model-name>` (e.g. `llama3.3`) and `hermes -p tester config set OPENAI_BASE_URL https://ollama.com/v1`
- [x] 6.4 Set Tester API key: `hermes -p tester config set OPENAI_API_KEY <your-ollama-api-key>`
- [x] 6.5 Set Tester toolsets: `hermes -p tester config set toolsets terminal,file,browser`
- [x] 6.6 Set Tester workspace: `hermes -p tester config set TERMINAL_CWD ~/workspace`
- [x] 6.7 Set Tester Slack tokens: `hermes -p tester config set SLACK_BOT_TOKEN xoxb-<app3-token>` and `hermes -p tester config set SLACK_APP_TOKEN xapp-<app3-token>`
- [x] 6.8 Set Tester allowed users: `hermes -p tester config set SLACK_ALLOWED_USERS <CEO-slack-member-id>`
- [x] 6.9 Verify Tester config: `hermes -p tester config` — confirm all values

## 7. Gateway Services Installation

- [x] 7.1 Enable systemd linger so services survive logout: `sudo loginctl enable-linger $USER`
- [x] 7.2 Install Support gateway as system service: `sudo hermes -p support gateway install --system`
- [x] 7.3 Install Developer gateway as system service: `sudo hermes -p developer gateway install --system`
- [x] 7.4 Install Tester gateway as system service: `sudo hermes -p tester gateway install --system`
- [x] 7.5 Start all three gateways: `sudo hermes -p support gateway start --system && sudo hermes -p developer gateway start --system && sudo hermes -p tester gateway start --system`
- [x] 7.6 Verify all three are active: run `hermes -p support gateway status --system`, `hermes -p developer gateway status --system`, `hermes -p tester gateway status --system` — each must show `active (running)`
- [x] 7.7 Confirm three distinct service units: `systemctl list-units | grep hermes-gateway` must show 3 entries

## 8. End-to-End Verification

- [ ] 8.1 Send a test message to `#support` in Slack — confirm Support bot responds in the correct persona (advisory, no terminal commands)
- [ ] 8.2 Send a test message to `#developer` in Slack — confirm Developer bot responds with technical persona and confirms terminal access
- [ ] 8.3 Send a test message to `#tester` in Slack — confirm Tester bot responds with QA persona
- [ ] 8.4 Test Support handoff flow: ask Support bot to investigate a sample issue → verify it creates a file in `~/workspace/support/handoffs/`
- [ ] 8.5 Test Developer handoff pickup: ask Developer bot to check for pending handoffs → verify it finds and reads the file from step 8.4
- [ ] 8.6 Test Tester validation: ask Tester bot to validate a fix → verify it writes a `validated-*.md` file to `~/workspace/support/handoffs/`
- [ ] 8.7 Reboot machine and verify all three gateway services automatically restart (`active (running)` after boot)

## 9. Version Control & Documentation (Optional but Recommended)

- [x] 9.1 Copy the three SOUL.md files into this devops repo as templates: `mkdir -p config/hermes-profiles && cp ~/.hermes/profiles/{support,developer,tester}/SOUL.md config/hermes-profiles/` (prefix each filename with its profile name)
- [x] 9.2 Copy the three `config.yaml` files (with secrets redacted) as reference templates: `config/hermes-profiles/<name>-config.yaml.template`
- [x] 9.3 Create `config/hermes-profiles/README.md` documenting: profile names, models used, Slack channel mapping, handoff convention, and gateway restart commands
- [x] 9.4 Add `~/.hermes/` to `.gitignore` to ensure secrets are never committed
