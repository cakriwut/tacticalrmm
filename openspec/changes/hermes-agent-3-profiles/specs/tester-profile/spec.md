## ADDED Requirements

### Requirement: Tester profile created and isolated
A Hermes profile named `tester` SHALL be created via `hermes profile create tester`. It MUST have its own isolated `~/.hermes/profiles/tester/` directory.

#### Scenario: Profile isolation confirmed
- **WHEN** `hermes profile list` is run
- **THEN** `tester` appears in the list with its own entry

### Requirement: Tester SOUL.md persona defined
The Tester profile's `SOUL.md` SHALL define the agent as a QA engineer focused on validation, edge cases, and test coverage. It MUST instruct the agent to: read Developer's implementation context from `~/workspace/support/handoffs/`, run test suites, validate behavior, identify edge cases, and write validation results to `~/workspace/support/handoffs/validated-YYYYMMDD-<topic>.md`.

#### Scenario: Validation result written
- **WHEN** Tester completes validation of a feature
- **THEN** a `validated-YYYYMMDD-<topic>.md` file is created in `~/workspace/support/handoffs/` with pass/fail status and findings

### Requirement: Tester model set to Ollama Cloud
The Tester profile `config.yaml` SHALL set the primary model to an Ollama Cloud model. The profile `.env` MUST contain `OPENAI_API_KEY` (Ollama API key) and `OPENAI_BASE_URL=https://ollama.com/v1`.

#### Scenario: Model resolves to Ollama
- **WHEN** `hermes -p tester config` is run
- **THEN** the model field resolves via the Ollama Cloud endpoint

### Requirement: Tester toolsets set to terminal, file, browser
The Tester profile `config.yaml` SHALL set `toolsets` to `terminal,file,browser`. Terminal and browser tools MUST be active; the full skills system is NOT required.

#### Scenario: Test suite execution available
- **WHEN** Tester agent is asked to run tests
- **THEN** the agent executes the test command via terminal and returns the output

### Requirement: Tester workspace set to ~/workspace
`TERMINAL_CWD` in the Tester profile `.env` SHALL be set to `~/workspace` (same as Developer, enabling access to the same codebase).

#### Scenario: Working directory confirmed
- **WHEN** Tester agent is asked "what is your current directory?"
- **THEN** it reports `~/workspace` or its absolute equivalent

### Requirement: Tester Slack bot connected
The Tester profile `.env` SHALL contain `SLACK_BOT_TOKEN` (xoxb-) and `SLACK_APP_TOKEN` (xapp-) for Slack App 3. `SLACK_ALLOWED_USERS` MUST be set to the CEO's Slack Member ID.

#### Scenario: Tester bot responds in #tester channel
- **WHEN** the CEO sends a message in the `#tester` Slack channel
- **THEN** the Tester Hermes agent responds within the same channel/thread
