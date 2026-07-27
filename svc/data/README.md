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

Tracked response samples and CAP fixtures in this directory are historical.
New development configuration and templates belong under
`svc/config/development`; generated development data belongs in
`svc/.runtime/development` or the development Compose named volume.
