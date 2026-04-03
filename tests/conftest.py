import os
# Change to the app/ directory so module-level file reads in app.py work correctly
# (index.html, etc.)
os.chdir(os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
