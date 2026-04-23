## ADDED Requirements

### Requirement: Scoped contributor group exists
A project group `newsdeepfake-contributors` SHALL exist in the `data-ai` Azure DevOps project with no project-level repository permissions assigned.

#### Scenario: Group created with no project permissions
- **WHEN** the `newsdeepfake-contributors` group is created in the `data-ai` project
- **THEN** the group SHALL have zero allow bits at the project-level Git Repositories ACL

### Requirement: Group has repo-level permissions on newsdeepfake only
The `newsdeepfake-contributors` group SHALL have an explicit ACL entry on the `newsdeepfake` repository granting allow=16406 (GenericRead + GenericContribute + CreateBranch + PullRequestContribute).

#### Scenario: Permissions granted on newsdeepfake
- **WHEN** the ACL for `newsdeepfake` is queried
- **THEN** the `newsdeepfake-contributors` group SHALL have allow bits: GenericRead (2), GenericContribute (4), CreateBranch (16), PullRequestContribute (16384)

#### Scenario: No permissions on other repos
- **WHEN** any other repository's ACL in `data-ai` is queried
- **THEN** the `newsdeepfake-contributors` group SHALL have no entry (no allow, no deny)

### Requirement: Gokulakrishnan is member of the scoped group
`gokulakrishnan.m@s2t.ai` SHALL be a member of `newsdeepfake-contributors` and SHALL have no other project group membership in `data-ai`.

#### Scenario: User can clone and push to newsdeepfake
- **WHEN** `gokulakrishnan.m@s2t.ai` authenticates and attempts to clone `newsdeepfake`
- **THEN** the operation SHALL succeed

#### Scenario: User can create a branch
- **WHEN** `gokulakrishnan.m@s2t.ai` pushes a new branch to `newsdeepfake`
- **THEN** the operation SHALL succeed

#### Scenario: User cannot access other repositories
- **WHEN** `gokulakrishnan.m@s2t.ai` attempts to access any repository other than `newsdeepfake`
- **THEN** the operation SHALL be denied with an access error
