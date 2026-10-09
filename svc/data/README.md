# Legacy production-compatible data directory

Do not use this directory for development.

The historical Compose deployment bind-mounted this host directory to
`/app/svc/data`, so the ignored `audit.db`, generated routines, and sensor
captures may be production data. The production Compose definition preserves
that container path through the explicit `SVC_PRODUCTION_DATA_DIR` setting.

Before upgrading a site deployment:

1. Run `scripts/production_preflight.py` against this directory.
2. Copy the site `sensors_config.json` to an external production configuration
   directory.
3. Set `SVC_PRODUCTION_DATA_DIR` to this directory's absolute host path.
4. Do not delete or rename `audit.db`.

This directory is runtime-only: git tracks nothing here except this README.
Former tracked files moved on 2026-10-08 (tag `archive/pre-cleanup-2026-10`
holds the old layout):

- `sensors_config.json` (the old full-site config) is in
  `docs/reference/sensors_config.legacy-site.json`, with its real COM ports and
  C-BOX host. The production template keeps the same T-10A and EKO sensor IDs,
  with `port: auto` and a placeholder host.
- `window_mapping.json` is retired; the Halio window UUIDs are tabulated in
  `docs/glazing_configuration.md`.
- `ResponseData/` Halio samples are test fixtures in `svc/tests/fixtures/halio/`;
  the bring-up logs are in `docs/halio/bring-up/`.
- `251118_Jeti_Spectraval_Data.cap` is a test fixture in `svc/tests/fixtures/`.
- `panels_config.json` duplicated `svc/config/development/panels_config.json`,
  and `routines/*.py` were generated example routines; both were removed.

New development configuration and templates belong under
`svc/config/development`; generated development data belongs in
`svc/.runtime/development` or the development Compose named volume.
