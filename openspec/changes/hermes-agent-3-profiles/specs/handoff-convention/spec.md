## ADDED Requirements

### Requirement: Handoff directory structure created
The directory `~/workspace/support/handoffs/` SHALL exist with an `archive/` subdirectory. Both directories MUST be created as part of setup.

#### Scenario: Directory structure present
- **WHEN** setup is complete
- **THEN** `ls ~/workspace/support/handoffs/` succeeds and `archive/` subdirectory exists

### Requirement: Support handoff file format
When Support escalates to Developer, it SHALL create a markdown file at `~/workspace/support/handoffs/YYYYMMDD-<topic-slug>.md` using the following structure:

```
## Issue Summary
<1-2 sentence description of the problem>

## Evidence
<relevant log excerpts, config snippets, error messages>

## Root Cause Analysis
<Support's diagnosis based on available information>

## Recommended Fix
<suggested resolution — what Developer should do>

## Files / Services Affected
<list of relevant paths, services, or components>
```

#### Scenario: Handoff file created with correct format
- **WHEN** Support writes a handoff for an authentication timeout issue
- **THEN** the file `~/workspace/support/handoffs/20260412-auth-timeout.md` exists and contains all five sections

#### Scenario: Handoff filename follows convention
- **WHEN** any handoff file is created
- **THEN** the filename matches the pattern `YYYYMMDD-<kebab-case-topic>.md`

### Requirement: Tester validation result format
When Tester completes validation, it SHALL write results to `~/workspace/support/handoffs/validated-YYYYMMDD-<topic-slug>.md` with the following structure:

```
## Validation Status
PASS | FAIL | PARTIAL

## What Was Tested
<list of test cases / scenarios run>

## Results
<per-test-case outcome>

## Edge Cases Found
<any issues discovered beyond the original scope>

## Notes
<observations for Developer or Support>
```

#### Scenario: Validation result file created
- **WHEN** Tester completes validation of a fix
- **THEN** a `validated-` prefixed file exists in `~/workspace/support/handoffs/` with all five sections

### Requirement: Handled handoffs archived
Processed handoffs (where Developer has implemented and Tester has validated) SHALL be moved to `~/workspace/support/handoffs/archive/` to keep the active directory clean.

#### Scenario: Archive keeps active handoffs directory clean
- **WHEN** a fix is fully validated
- **THEN** both the original handoff and its validated counterpart are moved to `archive/`
