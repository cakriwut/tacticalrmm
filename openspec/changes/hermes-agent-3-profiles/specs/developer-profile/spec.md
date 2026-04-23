## ADDED Requirements

### Requirement: Developer profile created and isolated
A Hermes profile named `developer` SHALL be created via `hermes profile create developer`. It MUST have its own isolated `~/.hermes/profiles/developer/` directory.

#### Scenario: Profile isolation confirmed
- **WHEN** `hermes profile list` is run
- **THEN** `developer` appears in the list with its own entry, separate from `support` and `tester`

### Requirement: Developer SOUL.md persona defined
The Developer profile's `SOUL.md` SHALL define the agent as a senior engineer focused on code quality, infrastructure, and technical problem-solving. It MUST instruct the agent to: check `~/workspace/support/handoffs/` for pending Support handoffs at session start, implement solutions based on handoff findings, and confirm completion back via the handoff file or Slack.

#### Scenario: Handoff awareness at session start
- **WHEN** a new Developer Slack session begins
- **THEN** the agent checks `~/workspace/support/handoffs/` and mentions any pending unvalidated handoff files

### Requirement: Developer model set to Anthropic Claude
The Developer profile `config.yaml` SHALL set the primary model to an Anthropic Claude model (Sonnet or higher). The profile `.env` MUST contain `ANTHROPIC_API_KEY`.

#### Scenario: Model resolves to Anthropic
- **WHEN** `hermes -p developer config` is run
- **THEN** the model field shows an `anthropic/` model identifier

### Requirement: Developer toolsets set to full power
The Developer profile `config.yaml` SHALL set `toolsets` to `terminal,file,web,code,skills`. All tool categories MUST be active.

#### Scenario: Terminal execution available
- **WHEN** Developer agent is asked to run a shell command
- **THEN** the agent executes it and returns the output

### Requirement: Developer workspace set to ~/workspace
`TERMINAL_CWD` in the Developer profile `.env` SHALL be set to `~/workspace`. This MUST be the default working directory for all Developer gateway sessions.

#### Scenario: Working directory confirmed
- **WHEN** Developer agent is asked "what is your current directory?"
- **THEN** it reports `~/workspace` or its absolute equivalent

### Requirement: Developer Slack bot connected
The Developer profile `.env` SHALL contain `SLACK_BOT_TOKEN` (xoxb-) and `SLACK_APP_TOKEN` (xapp-) for Slack App 2. `SLACK_ALLOWED_USERS` MUST be set to the CEO's Slack Member ID.

#### Scenario: Developer bot responds in #developer channel
- **WHEN** the CEO sends a message in the `#developer` Slack channel
- **THEN** the Developer Hermes agent responds within the same channel/thread
