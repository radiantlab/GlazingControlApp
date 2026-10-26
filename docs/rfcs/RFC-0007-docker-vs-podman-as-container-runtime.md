# RFC: Docker vs Podman As Container Runtime

- **Author:** Dominic Maluski
- **Date:** 2026-10-24
- **Status:** Proposed
- **Decision Date:** (fill when decided)
- **Deciders:** (who agreed to the outcome)
- **Superseded By:** —

## Problem and Context

The DIAL Control Center runs in production as a Linux container on the Windows PC in the DIAL trailer. The container is the only process that writes `audit.db`, which holds research history that cannot be
recreated (ADR 0004). The repository documents two ways to run that container, Podman and Docker, and does so inconsistently. `DEV-SETUP.md`, `docs/production_sensor_setup.md`,
`docs/on_site_sensor_checklist.md` and the restore procedure in `svc/README.md` give `podman compose` commands. CI (`.github/workflows/docker-builds.yml`) builds and validates with `docker`.
`scripts/sensors/README.md` says "Podman (or Docker if installed later)". Every container instruction is written for two runtimes, and a newcomer cannot tell which one the project officially supports. The
trailer itself currently runs Podman.

This RFC decides which container runtime the project supports and documents, and which one the trailer runs. Issue #86 records an informal team agreement to move to Docker, but no ADR exists, the issue is
still in `needs-triage`, and nothing has changed on the trailer. The decision is still open, and this RFC is meant to choose the one supported runtime for the DIAL Control Center.

It has to be decided now because two pieces of in-flight work build on the answer. The lifecycle script in #68 has to detect, start and diagnose one engine. Importantly, Docker and Podman treat permissions in quite different ways, and this could cause a few
different issues for the team. Using podman and docker interchangeably could result in database files with different user permissions. Supporting both means any change which had implications for
permissions would need to be checked twice, and we may get bugs which are harder to reproduce.

Changing the documentation is reversible. Changing the trailer is not cheap: it means installing software on a partner-owned machine, moving a running production stack that owns irreplaceable data, and
retraining operators. Each of those steps needs on-site access with the partner, which the team gets only occasionally. Doing nothing leaves every future doc, script and support conversation with two
answers, and opens the door for potential permissions-related bugs in the future.

## Options

### Option A: Docker Desktop on the trailer, Docker everywhere

Install Docker Desktop on the trailer PC, move the production stack from Podman to Docker against the same host data directory, and document only `docker compose` / `docker logs`.

- **Benefits:** one runtime across CI, development and production; CI already tests with Docker; #78's healthcheck was verified on Docker Desktop; Docker Compose is native rather than delegated to a
provider.
- **Costs:** an on-site migration with the partner; a licensing question for a university research lab (see Constraints); Docker Desktop is a large GUI install that has to be running before `docker`
works.
- **Right choice when:** the Docker Desktop licence clearly covers the trailer's use.

### Option B: Podman everywhere

Keep Podman on the trailer, standardize the documentation on `podman compose`, and switch CI to Podman so production and CI match.

- **Benefits:** no migration on the trailer; it is running there today; Apache-2.0 licensed with no subscription terms.
- **Costs:** the team found three Podman-specific failures on the trailer (below); CI needs rework; most developers use Docker locally and would have to switch or translate.
- **Right choice when:** the trailer cannot take a new install (partner refuses, or the licence question rules out Docker Desktop and Option C is not workable), or the Podman failures turn out to be
one-time setup problems.

### Option C: Docker Engine inside a WSL distribution, without Docker Desktop

Install the open-source Docker Engine and Compose plugin in a WSL 2 Linux distribution on the trailer, and document `docker compose` everywhere, as in Option A.

- **Benefits:** the same commands and CI as Option A; no Docker Desktop subscription terms; no GUI app or signed-in user for the double-click start to depend on.
- **Costs:** no supported Windows installer, so setup is manual Linux administration inside WSL; starting at boot is the team's job: `systemctl enable docker` needs systemd turned on in `/etc/wsl.conf`, and the distribution itself starts only when a scheduled task runs `wsl.exe`; fewer people on the team have done this.
- **Right choice when:** Option A is ruled out by licensing, but the team still wants one `docker` command set.

### Option D: Do nothing

Keep documenting both runtimes and leave the trailer on Podman.

- **Costs, and when they arrive:** immediately, #68 and #75 must support both engines; again at every on-site visit, when whoever is there must know which commands apply; and when a
new team inherits the project next year without the history in this document.
- **Right choice when:** neither runtime can be committed to yet, for example if the partner is about to replace the trailer PC.

## Analysis

**Performance** does not separate the options: all of them run the same OCI image built from the same `Dockerfile`.

**Complexity** is where they differ, and our own deployment is the evidence. On 2026-10-15 the team deployed production to the trailer with Podman and recorded three problems in #76 and the #68 proposal:

1. Podman 6 on Windows needed WSL 2.7.5 or newer. On older WSL every container failed with `netavark: nftables error`.
2. `podman compose ... --build` stopped with `can't stat '...\.pytest_cache'` on a folder the user could not read.
3. Each Windows user has their own Podman machine, and it is stopped after every reboot. A scheduled task running as `SYSTEM` will not see the operator's machine, which matters for #75's optional start
at boot.

The second problem is not purely Podman's. `podman compose` is "a thin wrapper around an external compose provider", and `docker-compose` takes precedence when it is installed [2]. On the trailer the
failing build was already running Docker's Compose code under Podman. The trailer's Podman path therefore depends on Docker tooling too, which weakens the case for Option B. The first problem is fixed
by updating WSL and should not recur. Docker Desktop does not solve the third either. Its only documented start-up option is "Start Docker Desktop when you sign in to your computer" [5], so it also needs a user session. The community workaround [6] creates one by turning on Windows auto-login with a stored password, then locking the screen, which is a security change to a partner-owned PC. Docker Engine in WSL (Option C) runs as an ordinary Linux service, though the WSL distribution itself still has to be started by a scheduled task.

**Maintainability** favors A and C. CI already validates the Compose file and builds the image with `docker` (`docker-builds.yml`), so with Docker on the trailer the image CI tests is built by the same
engine that runs it. ADR 0003 holds Python dependencies to that byte-for-byte standard, and the runtime is the one piece outside it. Option B would mean rewriting the CI job, and Option D is simply
kicking the can down the road for someone (likely us) to deal with later.

**Security and permissions** are where the two engines differ most, despite the shared interface. Rootless Podman runs containers as the user who started them: "root in the container is actually your user on the host", and a non-root container user is mapped through that user's subordinate ID range [7]. Docker runs containers through a root daemon and does not remap IDs, so the same image writes files with different owners under each engine. The trailer has already shown this boundary three times: the per-user Podman machine (#68), the `can't stat` failure on a folder owned by another account (#76), and #76's open question about running the container as a non-root user, whose answer would differ by engine for `audit.db`, the backups and the sensor cursors. Supporting one engine means one permission model to verify. Docker Desktop is also a larger privileged install on a machine we do not own, so it needs the partner's approval. In every option the Halio controller is reachable only from the trailer LAN (ADR 0005), and nothing here changes that.

**Uncertainties:**

- Whether Docker Desktop's free "Education" category covers a research lab at a university with far more than 250 employees [1]. We have not asked anyone at OSU.
- Whether Docker Desktop's WSL networking reaches the EKO C-BOX. #76 notes that the C-BOX sits on a direct link that WSL NAT does not route to under Podman. Docker Desktop also uses WSL, so this may not improve.
- Whether Docker Desktop can start unattended at boot. Docker documents only start at sign-in [5], and the community workaround depends on Windows auto-login [6]. Neither has been tested here, and this affects #75.

**Sources:**

1. Docker, "Docker Desktop license agreement," https://docs.docker.com/subscription/desktop-license/
2. Podman, `podman-compose(1)`, https://docs.podman.io/en/latest/markdown/podman-compose.1.html
3. Podman, `podman-machine(1)`, https://docs.podman.io/en/latest/markdown/podman-machine.1.html
4. Project issues #68, #75, #76, #86, and ADRs 0002–0005 in `docs/adr/`.
5. Docker, "Change your Docker Desktop settings," https://docs.docker.com/desktop/settings-and-maintenance/settings/
6. aash591, "windows-docker-boot-startup," GitHub, https://github.com/aash591/windows-docker-boot-startup, accessed 2026-10-25
7. Podman, "Basic Setup and Use of Podman in a Rootless environment," https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md

## Recommendation and Verification Plan

**Recommendation:** standardize on the `docker` command set (Options A or C), in two steps that separate the reversible part from the hard-to-reverse part.

1. **Now (reversible):** carry out the proposal for issue #86 in the repository. All docs, the in-app `SensorDocs.tsx`, the agent guidance, and the #68 lifecycle script target `docker compose`. Podman
stays as one compatibility note.
2. **On the next site visit (hard to reverse):** move the trailer from Podman to Docker. Ask OSU or the partner about the Docker Desktop licence before the visit. If it is clearly covered, install
Docker Desktop (A). If it is not, or nobody can say, install Docker Engine in WSL (C). Both run the same commands, so step 1 does not depend on the answer.

**Why it wins:** it removes the doubled documentation and the two-engine logic, leaves one permission model to verify, matches production to CI, and does not stake the trailer migration on an unanswered licensing question. Option B avoids
a migration but moves CI and every developer's local setup away from the tool they already use, and the trailer's Podman setup already runs Docker's Compose code anyway.

**Costs we accept:** one on-site migration with the partner, some Windows/WSL administration if we end up on Option C, and a short period in which the docs say `docker` while the trailer still runs Podman.

**Confidence:** medium. The repository change is low-risk. The trailer step depends on three things we have not tested: licence coverage, C-BOX networking under Docker, and start after reboot.

**Rollback path:** the production data lives in a host directory that both engines bind-mount, not in an engine volume. Podman stays installed with its stack stopped until the checks below pass for two
weeks. Rolling back is `docker compose down`, then `podman compose up -d` against the same directory.

**Verification:**

1. **Podman references** (every PR, added to CI): `grep -ril podman` outside `docs/rfcs/` and `docs/adr/` finds only the compatibility note. Detects doc drift returning.
2. **`docker-builds` CI job** (every PR): passes on `main`. Detects a broken image or Compose file.
3. **Database integrity** (site visit): `scripts/production_preflight.py` before and after the migration reports integrity `ok` and the same table row counts. Detects data lost or corrupted in the move.
4. **Health** (site visit): `GET /health` under Docker returns 200 with `environment: production` and `control_source: physical`. Detects wrong configuration or environment.
5. **Sensors** (site visit): each configured sensor shows fresh data in the HMI. Detects the C-BOX or LiVal capture being unreachable from Docker.
6. **File permissions** (site visit, after one hour under Docker): `audit.db` keeps updating, a new backup appears in `SVC_DB_BACKUP_DIR`, and `docker logs` shows no permission errors. Detects the container writing files the host or a later run cannot read.
7. **Reboot** (site visit): after rebooting the trailer PC, the double-click script brings the stack to healthy without opening a terminal. Detects the engine not coming back.
8. **Two-week soak** (before removing Podman): no data gaps attributable to the runtime. Detects problems that only show over time.

If the sensor or reboot checks fail on site, the team rolls back the same day and reopens this RFC with what it learned.

## Constraints

- **Licensing:** Podman and Docker Engine are Apache-2.0. Docker Desktop is free for "Education" and small businesses, while "professional use in larger organizations" needs a paid subscription [1].
Whether a university research lab falls under "Education" is the open question that decides between A and C. The project's GPL-3.0 licence is unaffected, because we do not distribute the runtime.
- **Data use:** `audit.db` holds the lab's research and sensor history. The migration must not copy it off the trailer, and the preflight backup stays in `SVC_DB_BACKUP_DIR` on the trailer.
- **IP:** none. Choosing a runtime creates no intellectual property.
- **Partner confidentiality boundary:** the trailer PC is partner-owned, so installing software on it needs the partner's approval and their presence on site.

## Delegation and Validation

- **What I handed to AI tools:** Claude Code searched the repository and issues for Podman references and trailer evidence, fetched the vendor documentation, drafted this RFC, then reviewed my revision and proposed fixes, each of which I approved or rejected individually.
- **What checks made that reasonable:** every project claim cites a file, issue or ADR that a reviewer can open; external claims link to vendor documentation; the `docker-builds` CI job and the pre-commit
hooks already exist and gate the repository half of the change; the trailer half has a rollback path that keeps the data directory in place.
- **Where I stopped and validated the result myself, and why those points:** I rejected the draft's framing that supporting two engines doubles the test matrix, since the engines share an interface; the real risk is their different permission models, which the draft had not mentioned, so I made that the central argument. I researched whether Docker Desktop can start without a sign-in, because #75 depends on it: Docker documents only start at sign-in [5], and the community workaround [6] needs Windows auto-login, which I have not tested and the partner would need to approve. Before the trailer migration I will personally confirm the licence question and run the verification checks on site, because that step is hard to reverse.

## Decision

Proposed, until the team decides.
