import os
import sys
from pathlib import Path

# Change to the app/ directory so module-level file reads in app.py work correctly
# (templates/, conf/, etc.), and add it to sys.path so app modules are importable.
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app")
ROOT_DIR = Path(APP_DIR).parent
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)


def pytest_configure(config):
    if getattr(config.option, "xmlpath", None):
        return
    if not any("test_container_smoke_test.py" in str(arg) for arg in getattr(config, "args", [])):
        return

    test_results_dir = ROOT_DIR / "test-results"
    test_results_dir.mkdir(exist_ok=True)
    config.option.xmlpath = str(test_results_dir / "container_smoke_test.xml")
