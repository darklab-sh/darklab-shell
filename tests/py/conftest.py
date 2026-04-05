import os
import sys

# Change to the app/ directory so module-level file reads in app.py work correctly
# (templates/, conf/, etc.), and add it to sys.path so app modules are importable.
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app")
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)
