# Production configuration template

Copy this directory outside the repository, update `sensors_config.json` for
the site hardware, and mount it read-only at `/app/svc/config`.

Never place secrets in this directory. `HALIO_API_URL` and `HALIO_SITE_ID` are
supplied through the production environment file. The Halio v3 API needs no
API key.
