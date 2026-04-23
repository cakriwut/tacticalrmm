## ADDED Requirements

### Requirement: Support profile created and isolated
A Hermes profile named `support` SHALL be created via `hermes profile create support`. It MUST have its own isolated `~/.hermes/profiles/support/` directory containing `config.yaml`, `.env`, `SOUL.md`, `memories/`, and `sessions/`.

#### Scenario: Profile isolation confirmed
- **WHEN** `hermes profile list` is run
- **THEN** `support` appears in the list with its own entry

### Requirement: Support SOUL.md persona defined
The Support profile's `SOUL.md` SHALL define the agent as a patient, knowledgeable first-responder focused on: general knowledge Q&A, reading logs and config files (read-only), advising on fixes, drafting communications, and producing structured handoff files for Developer when technical action is needed. It MUST instruct the agent to create handoff files at `~/workspace/support/handoffs/YYYYMMDD-<topic>.md` when escalating.

#### Scenario: Persona loaded on session start
- **WHEN** the Support Slack bot receives a message
- **THEN** the agent responds with Support persona behavior (patient tone, advisory focus, no terminal execution)

#### Scenario: Handoff instruction followed
- **WHEN** Support encounters an issue requiring code changes or infra action
- **THEN** the agent creates a structured markdown file in `~/workspace/support/handoffs/` and notifies the user of the filename

### Requirement: Support model set to zAI (GLM)
The Support profile `config.yaml` SHALL set the primary model to a zAI GLM model. The profile `.env` MUST contain `ZAI_API_KEY` (or `GLM_API_KEY`). `GLM_BASE_URL` SHALL be set to `https://api.z.ai/api/paas/v4`.

#### Scenario: Model resolves to zAI
- **WHEN** `hermes -p support config` is run
- **THEN** the model field shows a zAI/GLM model identifier

### Requirement: Support toolsets restricted to web and file
The Support profile `config.yaml` SHALL set `toolsets` to `web,file` only. Terminal execution tools MUST NOT be active for this profile.

#### Scenario: Terminal tools absent
- **WHEN** Support agent is asked to run a shell command
- **THEN** the agent declines or advises it cannot execute commands, redirecting to Developer

### Requirement: Support workspace set to ~/workspace/support
`TERMINAL_CWD` in the Support profile `.env` SHALL be set to `~/workspace/support`. This MUST be the default working directory for all Support gateway sessions.

#### Scenario: Working directory confirmed
- **WHEN** Support agent is asked "what is your current directory?"
- **THEN** it reports `~/workspace/support` or its absolute equivalent

### Requirement: Support Slack bot connected
The Support profile `.env` SHALL contain `SLACK_BOT_TOKEN` (xoxb-) and `SLACK_APP_TOKEN` (xapp-) for Slack App 1. `SLACK_ALLOWED_USERS` MUST be set to the CEO's Slack Member ID.

#### Scenario: Support bot responds in #support channel
- **WHEN** the CEO sends a message in the `#support` Slack channel (mentioning or DMing the bot)
- **THEN** the Support Hermes agent responds within the same channel/thread
