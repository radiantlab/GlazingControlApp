from __future__ import annotations
import os

# Service mode: "sim" for the built in simulator or "real" for the trailer adapter
MODE = os.getenv("SVC_MODE", "sim").lower()

# Minimum seconds between level changes per panel
MIN_DWELL_SECONDS = int(os.getenv("SVC_MIN_DWELL_SECONDS", "20"))

# Path for durable state and audit log
# Get the svc directory (parent of app directory where this file lives)
_SVC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("SVC_DATA_DIR", "data")
# Legacy file (for migration)
PANELS_FILE = os.path.join(_SVC_DIR, DATA_DIR, "panels.json")
# New separated files
PANELS_CONFIG_FILE = os.path.join(_SVC_DIR, DATA_DIR, "panels_config.json")
PANELS_STATE_FILE = os.path.join(_SVC_DIR, DATA_DIR, "panels_state.json")
AUDIT_FILE = os.path.join(_SVC_DIR, DATA_DIR, "audit.json")
AUDIT_DB_FILE = os.path.join(_SVC_DIR, DATA_DIR, "audit.db")

# Halio API configuration (for real mode)
# NOTE: The previous default ("http://192.168.2.200:8084/api") was trailer-specific.
# For other deployments, override HALIO_API_URL via environment variable.
HALIO_API_URL = os.getenv("HALIO_API_URL", "http://localhost:8084/api")
HALIO_SITE_ID = os.getenv("HALIO_SITE_ID", "")
HALIO_API_KEY = os.getenv("HALIO_API_KEY", "")

# Panel to Halio Window UUID mapping file
WINDOW_MAPPING_FILE = os.path.join(_SVC_DIR, DATA_DIR, "window_mapping.json")
