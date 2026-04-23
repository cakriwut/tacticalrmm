## ADDED Requirements

### Requirement: Hermes Agent binary installed
Hermes Agent SHALL be installed via the official install script (`curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash`) on the host machine. The `hermes` binary MUST be available on `PATH` after sourcing `~/.bashrc`.

#### Scenario: Successful installation
- **WHEN** the install script is executed on Linux
- **THEN** the `hermes` binary is available at `~/.local/bin/hermes` and `hermes --version` returns a version string without error

#### Scenario: Base setup completed
- **WHEN** `hermes setup` is run after installation
- **THEN** `~/.hermes/config.yaml` and `~/.hermes/.env` are created and the default profile is configured

### Requirement: Python 3.11 prerequisite satisfied
The system SHALL have Python 3.11 available before installation. The install script MUST complete without Python version errors.

#### Scenario: Python version check passes
- **WHEN** the install script checks for Python
- **THEN** Python 3.11.x is found and installation proceeds without version-related errors

### Requirement: uv package manager available
The `uv` package manager SHALL be installed (via `curl -LsSf https://astral.sh/uv/install.sh | sh`) to manage Hermes's Python environment.

#### Scenario: uv available post-install
- **WHEN** hermes installation completes
- **THEN** `uv --version` returns successfully
