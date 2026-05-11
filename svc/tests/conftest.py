import os

# Keep API tests in simulator mode even when a local svc/.env is configured for real hardware.
os.environ.setdefault("SVC_MODE", "sim")
