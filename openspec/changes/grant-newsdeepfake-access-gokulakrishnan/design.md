## Context

The `data-ai` Azure DevOps project contains 188 repositories. Standard project group membership (Contributors, Readers) grants permissions across all repos via inheritance. `newsdeepfake` repo has `inheritPermissions = True`, meaning all project-level group permissions flow down automatically.

The existing pattern for scoped access (observed on `shruthi.b@s2t.ai`) uses a direct user ACL entry on the repo. However, a direct ACL entry alone does not grant project access — the user also needs project membership. A dedicated group is a cleaner, repeatable pattern.

**Current state of `newsdeepfake` repo:**
- `inheritPermissions = True`
- One explicit user override: `shruthi.b@s2t.ai` (allow=228990)
- No existing scoped-access group

**Constraint:** The PAT token (`AZURE_DEVOPS_PAT` in Doppler) has permissions for: ACL reads/writes, project/team reads, repo lists. It does NOT have Graph/Identity scope for user entitlement management.

## Goals / Non-Goals

**Goals:**
- `gokulakrishnan.m@s2t.ai` can clone, push, create branches, and open PRs on `newsdeepfake`
- Access is scoped — no read or write access to any other repo in `data-ai`
- Solution is repeatable — the group can be reused for future users needing same scoped access

**Non-Goals:**
- Hiding repo names from the list view (requires Deny on all other repos or separate project — out of scope)
- Changing permissions for any existing user or group
- Modifying `inheritPermissions` on `newsdeepfake` (leave as-is)

## Decisions

### Decision 1: Project group over direct user ACL
**Chosen**: Create `newsdeepfake-contributors` group, grant permissions on repo, add user to group.  
**Alternative**: Direct user ACL entry (as done for shruthi.b).  
**Rationale**: Groups are reusable. Direct ACL entries are hard to audit and don't scale. If another person needs the same access later, they just join the group.

### Decision 2: Permissions live only at repo level
**Chosen**: Group has zero project-level permissions. Read+Contribute+CreateBranch granted only on `newsdeepfake` repo security.  
**Alternative**: Grant permissions at project level with Deny overrides on all other repos.  
**Rationale**: 188 repos makes Deny-everywhere impractical. Repo-level grant is surgically precise.

### Decision 3: Required permission bits
Grant these bits on `newsdeepfake` for `newsdeepfake-contributors`:
- `GenericRead` (2) — clone, browse, pull
- `GenericContribute` (4) — push commits
- `CreateBranch` (16) — create new branches
- `PullRequestContribute` (16384) — open and interact with PRs

Total allow value: `16406`

### Decision 4: Group creation method
Use ADO REST API (`POST /_apis/graph/groups`) since the PAT has sufficient scope for group management. User must be invited to the org first (requires org-level admin action if not already a member).

## Risks / Trade-offs

- **[Risk] User sees 187 other repo names** → Accepted trade-off. They get Access Denied on click. Fully hiding names requires separate project (out of scope).
- **[Risk] PAT may lack Graph scope for group creation** → Mitigation: test group creation API call first; fall back to manual UI step if 401.
- **[Risk] Gokulakrishnan not yet in the org** → Mitigation: check org membership first; if absent, provide instructions for manual invite via ADO UI (requires org owner).

## Migration Plan

1. Check if `gokulakrishnan.m@s2t.ai` is already an org member
2. Create `newsdeepfake-contributors` group in `data-ai` project
3. Set ACL on `newsdeepfake` repo: allow=16406 for the new group
4. Add Gokulakrishnan to the group
5. Verify: confirm he can see and clone the repo, confirm he cannot access another repo

**Rollback**: Remove user from group OR remove group's ACL entry from `newsdeepfake`.

## Open Questions

- Is Gokulakrishnan already a member of the `predictintel` ADO organization? (Need to verify — may require manual invite)
