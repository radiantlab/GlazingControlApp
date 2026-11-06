# Risks

The one risk register for the DIAL Control Center. It covers business,
technical, and team risks, and every external prerequisite the work waits on.
Update it between checkpoints: re-rank, close what is done, and add what is new.

- **Last updated:** 2026-10-29
- **Rank:** 1 is the most urgent. Ranked by likelihood times impact, with ties
  broken by how hard the damage is to undo.
- **Likelihood and impact:** High, Medium, or Low.

## Risk Register

| Rank | Risk | Type | Likelihood | Impact | Owner | Mitigation | Status |
| :---: | :--- | :--- | :---: | :---: | :--- | :--- | :--- |
| 1 | Production backups have never been restored, so a failed or corrupt `audit.db` could lose research history that cannot be recreated (ADR 0004). | Technical | Medium | High | **TODO(team)** | Confirm the backup worker runs on the trailer; restore a backup to a scratch location and check its readings (requirements item 1); #83. | Open |
| 2 | Some tint requests to Halio are lost without an error, and tint behaves as on/off instead of 0 to 100, so a study can run under the wrong glazing state. | Technical | High | High | **TODO(team)** | Reproduce, find where requests drop, surface every failure in the HMI and audit log, and add tests for Halio being unreachable (requirements item 3). | Open |
| 3 | Sensor dropouts are stored as gaps, not failures, and the EKO has no staleness check, so missing readings can be mistaken for valid data. | Technical | Medium | High | **TODO(team)** | Report connected, stale, or failed per instrument and record dropouts with start and end times (requirements item 2). | Open |
| 4 | Work on the trailer needs on-site access with the partner, which the team gets only occasionally, so verification and migrations can slip by weeks. | Business | High | Medium | **TODO(team)** | Batch on-site checks into scheduled visits; use `docs/on_site_sensor_checklist.md`; ask for visits early (see External Prerequisites). | Open |
| 5 | Metric names and units are chosen per driver, and renaming them after studies record data means migrating historical rows. | Technical | Medium | Medium | Calvin Grabowski | Decide RFC-0006 before more instruments or study data are added. | RFC-0006 Proposed |
| 6 | Routines run user-written Python from the HMI as subprocesses and have no tests, so a bad routine can stall the service or command the glazing unexpectedly. | Technical | Low | High | **TODO(team)** | Keep the service LAN-only (ADR 0005); add tests for starting, stopping, and failing routines. | Open |
| 7 | Operators cannot start the system without a terminal, so a missed step leaves the Sensor Agent or the service down during a study. | Business | Medium | Medium | **TODO(team)** | One-click startup and an operator guide (epic #75, #68, #95, #96). | In progress |
| 8 | Knowledge of the trailer setup sits with a few people, and team members leave at the end of the year. | Team | Medium | Medium | **TODO(team)** | Keep setup and decisions in the repository (`DEV-SETUP.md`, ADRs, this register), not in chat. | Ongoing |
| 9 | Lint and the PowerShell tests do not run in CI yet, so regressions in the HMI and the operator scripts can merge unnoticed. | Technical | Medium | Low | Calvin Grabowski | Add Biome and Pester to CI (#59, #91); run the lifecycle-script suite too (#96). | In progress |

## External Prerequisites

Approvals, accounts, and reviews the work waits on, with who asked and when.

| Prerequisite | Needed for | Asked by | Asked of | Date asked | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Agreement on the production target (the trailer PC, see the deployment section of `docs/design.md`) | Repo Checkpoint 1 milestone | **TODO(team)** | Project partner | **TODO(team)** | **TODO(team)** |
| Docker Desktop licence covers the trailer's use | ADR 0007 | Dominic Maluski | **TODO(team)** | **TODO(team)** | Open |
| Permission to install remote-access software (Tailscale) on the trailer PC | Requirements item 6 | **TODO(team)** | Project partner | Not asked yet | Not asked |
| On-site visit to verify backups, sensors, and Halio control | Risks 1 to 4 | **TODO(team)** | Project partner | **TODO(team)** | **TODO(team)** |
| Add `powershell-tests` as a required check in ruleset 24736232 | #59 | Calvin Grabowski | Repository admin | 2026-10-28 (PR #91) | Waits on #91 merging |

## Staging and Rollback Plan

**Where changes are exercised before they reach users.**

1. **CI on every pull request** (in place): backend tests, frontend checks, and
   Docker builds must pass before a squash merge to `main`.
2. **Development stack with simulators** (in place): every change runs locally
   against the panel and sensor simulators, which need no hardware.
3. **Trailer check before operators use a build** (planned, lands
   **TODO(team): date**): on a site visit, start the new build with the
   lifecycle script, run its health check and
   `docs/on_site_sensor_checklist.md`, and only then hand it to operators.

**How a bad change is undone.**

1. **Code** (in place): revert the squash-merged commit on `main` through a
   pull request; each change is one commit, so one revert removes it.
2. **Trailer deployment** (planned, lands **TODO(team): date**): note the
   commit running on the trailer before each update, and roll back by checking
   out that commit and restarting with the lifecycle script.
3. **Data** (planned, lands **TODO(team): date**): restore `audit.db` from
   `SVC_DB_BACKUP_DIR` using the procedure in
   [`svc/README.md`](../svc/README.md#database-backups). This depends on risk 1:
   the restore must be proven on the trailer first.
