## ADDED Requirements

### Requirement: Three concurrent gateway systemd services installed
Each of the three profiles SHALL have its own `hermes-gateway-<hash>` systemd service installed as a boot-time system service via `sudo hermes -p <name> gateway install --system`. All three MUST be able to run concurrently without port or PID conflicts.

#### Scenario: All three gateways active simultaneously
- **WHEN** the machine boots and all three services are enabled
- **THEN** `hermes -p support gateway status --system`, `hermes -p developer gateway status --system`, and `hermes -p tester gateway status --system` each return `active (running)`

#### Scenario: No service name collision
- **WHEN** all three gateways are installed
- **THEN** `systemctl list-units | grep hermes-gateway` shows three distinct service unit names

### Requirement: Gateways survive logout and reboot
The gateway services SHALL be configured as boot-time system services (`--system` flag) so they run without the CEO being logged in. `loginctl enable-linger` MUST be enabled for the user.

#### Scenario: Gateway running after user logout
- **WHEN** the user logs out and logs back in
- **THEN** all three gateway services are still in `active (running)` state

#### Scenario: Gateway running after system reboot
- **WHEN** the machine reboots
- **THEN** all three gateway services automatically start and reach `active (running)` without manual intervention

### Requirement: Per-profile gateway log access
Each gateway's logs SHALL be accessible via `journalctl` scoped to its service unit name.

#### Scenario: Support gateway logs accessible
- **WHEN** `journalctl -u hermes-gateway-<support-hash> -f` is run
- **THEN** live gateway log output for the Support profile is shown

### Requirement: Gateway health monitoring
Each profile MUST support `hermes -p <name> gateway status --system` for health checks. The command SHALL return the current state (active/inactive/failed) without requiring interactive session.

#### Scenario: Status check non-interactive
- **WHEN** `hermes -p developer gateway status --system` is run from a script
- **THEN** it exits 0 if active, non-zero if not, with status output to stdout
