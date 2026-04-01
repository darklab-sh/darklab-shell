import os
# Change to the app/ directory so module-level file reads in app.py work correctly
# (index.html, allowed_commands.txt, config.yaml, etc.)
os.chdir(os.path.dirname(os.path.dirname(__file__)))
