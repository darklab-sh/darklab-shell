"""
Flask extension singletons initialized without an app so blueprints can import
them before the Flask app object is created.

Usage in app.py:
    from extensions import limiter
    limiter.init_app(app)
"""

from flask_limiter import Limiter

from helpers import get_client_ip
from process import REDIS_URL, redis_client

limiter = Limiter(
    key_func=get_client_ip,
    default_limits=[],
    storage_uri=REDIS_URL if redis_client else "memory://",
)
