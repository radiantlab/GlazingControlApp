# 0007. Docker is the only supported container runtime

The service runs in production as a Linux container on the trailer's Windows PC, and the docs
used to describe that container twice, once with `podman` and once with `docker`, inconsistently
enough that a reader could not tell which one the project supported. We chose Docker as the
single documented and supported runtime: Docker Engine on Linux, and on the trailer either
Docker Desktop or Docker Engine inside a WSL 2 distribution, which run the same `docker compose`
commands. CI already builds and validates the image with `docker`, so production now runs the
engine CI tests. The two engines also treat file ownership differently, since rootless Podman
maps container users onto the host user's ID range while Docker does not, so supporting one
engine leaves one permission model to verify for `audit.db`, the backups, and the sensor cursors.
As a consequence, every container instruction in the docs, the in-app sensor docs, scripts, and
agent guidance is written once with `docker compose` and `docker logs`, and Podman appears only
in a single note in `DEV-SETUP.md` saying it reads the same Compose files but is not supported.
The Compose files keep Podman-compatible syntax, and nothing in them is Docker-only. The trailer
still runs Podman when this is written; moving it is an on-site migration with the partner that
keeps the same host data directory and has a same-day rollback, and until it happens the docs
describe the target rather than the trailer. The options and evidence, including the Docker
Desktop licensing question that decides between Docker Desktop and Docker Engine in WSL, are in
RFC-0007 (PR #90).
