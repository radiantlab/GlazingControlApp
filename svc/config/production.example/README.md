# Production configuration template

Copy this directory outside the repository, update `sensors_config.json` for
the site hardware, and mount it read-only at `/app/svc/config`.

Never place API keys in this directory. Halio credentials are supplied through
the production environment file.
