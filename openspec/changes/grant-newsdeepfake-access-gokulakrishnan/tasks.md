## 1. Pre-flight Checks

- [x] 1.1 Verify `gokulakrishnan.m@s2t.ai` is already a member of the `predictintel` ADO organization (if not, manual invite required before proceeding)
- [x] 1.2 Confirm `newsdeepfake` repo ID is `a839a2bb-e1ed-4f8a-bacc-9315a464d6d7` and `data-ai` project ID is `183c4e10-d23a-486e-9357-9500b9a74ee4`

## 2. Create Scoped Group

- [x] 2.1 Create project group `newsdeepfake-contributors` in `data-ai` via ADO REST API (`POST /graph/groups`)
- [x] 2.2 Verify group was created and capture its descriptor/SID for ACL use

## 3. Set Repo-Level Permissions

- [x] 3.1 Add ACL entry on `newsdeepfake` for `newsdeepfake-contributors` with allow=16406 (GenericRead=2 + GenericContribute=4 + CreateBranch=16 + PullRequestContribute=16384) via `POST /_apis/accesscontrollists/{git-ns}`
- [x] 3.2 Verify ACL entry is set correctly by querying `newsdeepfake` repo ACL

## 4. Add User to Group and Project

- [x] 4.1 Add `gokulakrishnan.m@s2t.ai` to the `data-ai` project as a bare member (no default group)
- [x] 4.2 Add `gokulakrishnan.m@s2t.ai` to `newsdeepfake-contributors` group

## 5. Verification

- [x] 5.1 Confirm `newsdeepfake-contributors` group has no project-level ACL entry (allow=0 or no entry at `repoV2/{project_id}`)
- [x] 5.2 Confirm `newsdeepfake-contributors` group ACL on `newsdeepfake` shows allow=16406
- [x] 5.3 Confirm Gokulakrishnan is a member of `newsdeepfake-contributors` and no other project group
