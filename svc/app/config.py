from __future__ import annotations
import os

# Service mode: "sim" for the built in simulator or "real" for the trailer adapter
MODE = os.getenv("SVC_MODE", "sim").lower()

# Minimum seconds between level changes per panel
MIN_DWELL_SECONDS = int(os.getenv("SVC_MIN_DWELL_SECONDS", "20"))

# Path for durable state and audit log
DATA_DIR = os.getenv("SVC_DATA_DIR", "data")
PANELS_FILE = os.path.join("svc", DATA_DIR, "panels.json")
AUDIT_FILE = os.path.join("svc", DATA_DIR, "audit.json")

# Halio API configuration (for real mode)
HALIO_API_URL = os.getenv("HALIO_API_URL", "https://api.halio.com")
HALIO_SITE_ID = os.getenv("HALIO_SITE_ID", "")
HALIO_API_KEY = os.getenv("HALIO_API_KEY", "")

# Panel to Halio Window UUID mapping file
WINDOW_MAPPING_FILE = os.path.join("svc", DATA_DIR, "window_mapping.json")