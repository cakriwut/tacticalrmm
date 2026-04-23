## ADDED Requirements

### Requirement: Passwords stored as bcrypt hashes
The `gs-mgt-server` MongoDB `users` collection SHALL store passwords as bcrypt hashes (cost factor ≥ 12). Plaintext password storage is prohibited.

#### Scenario: New password is stored as bcrypt hash
- **WHEN** a user account is created or a password is changed
- **THEN** the password stored in MongoDB is a bcrypt hash, not plaintext

#### Scenario: Existing plaintext passwords are migrated
- **WHEN** the migration script is run against the existing `users` collection
- **THEN** all documents with plaintext `password` fields are updated to bcrypt hashes

### Requirement: Login handler compares bcrypt hashes
The login handler SHALL use bcrypt compare to verify the submitted password against the stored hash. Direct plaintext string comparison is prohibited.

#### Scenario: Correct password grants access
- **WHEN** a user submits their correct plaintext password at login
- **THEN** the bcrypt comparison succeeds and the session is established

#### Scenario: Incorrect password is rejected
- **WHEN** a user submits an incorrect plaintext password at login
- **THEN** the bcrypt comparison fails and the service returns HTTP 401

#### Scenario: Legacy plaintext record is rejected before migration
- **WHEN** a plaintext password record exists in the database (pre-migration) and a user attempts to log in
- **THEN** the bcrypt comparison correctly fails (plaintext ≠ bcrypt hash), preventing authentication until migration runs

### Requirement: Migration script is idempotent
The one-time migration script SHALL be safe to run multiple times. Re-running it on already-migrated accounts SHALL NOT corrupt the stored bcrypt hash.

#### Scenario: Already-migrated account is skipped
- **WHEN** the migration script encounters a password field already in bcrypt format (starts with `$2b$`)
- **THEN** the document is skipped and left unchanged

### Requirement: Password hashing unit tests
The login handler and migration script SHALL have unit test coverage. Tests MUST cover: bcrypt compare success, bcrypt compare failure, migration idempotency, migration of plaintext record.

#### Scenario: Unit test suite passes
- **WHEN** the test suite for password hashing is run
- **THEN** all tests pass with zero failures
