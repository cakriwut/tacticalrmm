## ADDED Requirements

### Requirement: Hardcoded credentials removed from shipped bundle
The `gs-web-app` JS bundle SHALL NOT contain plaintext credentials, API tokens, or Basic Auth values. The `crawler_user` Basic Auth credential in `axios.js` and the Facebook Graph API token in `config.js` SHALL be removed from source code and injected at runtime via environment variables or server-side proxy.

#### Scenario: Bundle contains no hardcoded credentials after fix
- **WHEN** the production JS bundle is scanned for known credential patterns
- **THEN** no plaintext passwords, Basic Auth values, or API tokens are found

#### Scenario: Rotated credentials do not require a code change
- **WHEN** the `crawler_user` password is rotated
- **THEN** only the server-side environment variable / secret needs updating, not the JS source code

### Requirement: Plaintext password field removed from API calls
The `__ptxt` field SHALL be removed from all API requests in `ChangePassword.vue` and `AddUser.vue`. Plaintext passwords SHALL NOT be transmitted in any request body.

#### Scenario: Change password request contains no plaintext
- **WHEN** a user submits the change password form
- **THEN** the outgoing API request body does not contain a `__ptxt` field

#### Scenario: Add user request contains no plaintext
- **WHEN** an admin creates a new user via the add user form
- **THEN** the outgoing API request body does not contain a `__ptxt` field

### Requirement: Client-side SHA-1 hashing replaced with server-side verification
SHA-1 password hashing in the frontend (`GSLogin.vue`, `ChangePassword.vue`, `AddUser.vue`) SHALL be removed. Password verification SHALL be performed server-side using bcrypt (dependent on `mgt-server-password-hashing` capability being deployed first).

#### Scenario: Login does not compute SHA-1 in the browser
- **WHEN** a user logs in
- **THEN** the frontend does not invoke SHA-1 or any other client-side hash function on the password

### Requirement: Role and permission checks are enforced server-side
The `isAdmin()` check and `PermissionManager.js` SHALL NOT rely solely on `localStorage.depRole` as the source of truth. UI elements may use local state for rendering, but all privileged actions (route access, admin operations) SHALL be gated by a server-side authorization response.

#### Scenario: localStorage manipulation does not grant admin access
- **WHEN** a non-admin user manually sets `localStorage.app.auth.currentUser.depRole = "SUPER_ADMIN"` in DevTools
- **THEN** privileged API calls return 401/403 from the server

### Requirement: Credential hygiene unit/integration tests
Tests SHALL verify: no `__ptxt` in request payloads, admin API calls are rejected for non-admin users regardless of localStorage state.

#### Scenario: Test suite passes
- **WHEN** the credential hygiene test suite is run
- **THEN** all tests pass with zero failures
