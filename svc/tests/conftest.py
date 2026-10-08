import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest


# Keep the test suite isolated from both the ignored site configuration and the
# production database bind-mounted from svc/data.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="glazing-control-tests-")
atexit.register(shutil.rmtree, _TEST_DATA_DIR, ignore_errors=True)

_SVC_DIR = Path(__file__).resolve().parent.parent
os.environ["SVC_ENVIRONMENT"] = "development"
os.environ["SVC_MODE"] = ""
os.environ["SVC_DATA_DIR"] = _TEST_DATA_DIR
os.environ["SVC_CONFIG_DIR"] = str(_SVC_DIR / "config" / "development")
os.environ["SVC_DB_BACKUP_INTERVAL_HOURS"] = "0"
os.environ["SVC_DB_BACKUP_DIR"] = ""


@pytest.fixture(autouse=True)
def _reset_sensor_manager_health():
    """Prevent background-worker health state from leaking between tests."""
    from app.sensors import manager

    with manager._sensor_errors_lock:
        manager._sensor_errors.clear()
    yield
    with manager._sensor_errors_lock:
        manager._sensor_errors.clear()
