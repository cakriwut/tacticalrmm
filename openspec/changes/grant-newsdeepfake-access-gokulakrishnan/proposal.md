## Why

`gokulakrishnan.m@s2t.ai` needs contributor-level access to the `newsdeepfake` repository in the `data-ai` Azure DevOps project without being exposed to any of the other 187 repositories in the project. Adding him to the standard `Contributors` group would grant access to all repos, which is unacceptable.

## What Changes

- Create a new Azure DevOps project group `newsdeepfake-contributors` with **no project-level permissions**
- Grant `Read + Contribute + CreateBranch` permissions to this group **at the `newsdeepfake` repo level only**
- Add `gokulakrishnan.m@s2t.ai` to the `data-ai` project as a bare member (no default group assignment)
- Add `gokulakrishnan.m@s2t.ai` to the `newsdeepfake-contributors` group

## Capabilities

### New Capabilities
- `newsdeepfake-repo-access`: Scoped contributor access to a single repository via a dedicated group with repo-level-only permissions

### Modified Capabilities
<!-- None — no existing spec requirements are changing -->

## Impact

- **Azure DevOps project**: `data-ai` (`183c4e10-d23a-486e-9357-9500b9a74ee4`)
- **Repository**: `newsdeepfake` (`a839a2bb-e1ed-4f8a-bacc-9315a464d6d7`)
- **User**: `gokulakrishnan.m@s2t.ai`
- **No code changes** — this is a pure ADO configuration change via REST API
- **Other repos unaffected** — group has no project-level permissions, so all other 187 repos remain inaccessible to this user
- **Visibility caveat**: User will see other repo names in the list as a project member, but will receive Access Denied on any repo other than `newsdeepfake`
