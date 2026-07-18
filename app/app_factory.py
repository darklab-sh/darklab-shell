# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Generic Flask construction helper used by app.create_app."""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from flask import Flask


def create_app(
    config: Mapping[str, Any] | None = None,
    *,
    import_name: str = "app",
    template_folder: str = "templates",
    limiter_extension: Any = None,
    limiter_storage_uri: str | None = None,
    jinja_globals: Mapping[str, Any] | None = None,
    blueprints: Iterable[Any] = (),
    error_handlers: Mapping[Any, Callable[..., Any]] | None = None,
    before_request_handlers: Iterable[Callable[[], Any]] = (),
    after_request_handlers: Iterable[Callable[[Any], Any]] = (),
) -> Flask:
    """Build a Flask app from explicitly supplied registration pieces."""
    app = Flask(import_name, template_folder=template_folder)
    active_config = {} if config is None else config
    flask_config = {str(key): value for key, value in active_config.items() if str(key).isupper()}
    app.config.update(flask_config)
    if "RATELIMIT_ENABLED" not in flask_config:
        app.config["RATELIMIT_ENABLED"] = active_config.get("rate_limit_enabled", True)
    if limiter_storage_uri is not None:
        app.config["RATELIMIT_STORAGE_URI"] = limiter_storage_uri

    if limiter_extension is not None:
        limiter_extension.init_app(app)

    if jinja_globals:
        app.jinja_env.globals.update(jinja_globals)

    for code_or_exception, handler in (error_handlers or {}).items():
        app.register_error_handler(code_or_exception, handler)

    for handler in before_request_handlers:
        app.before_request(handler)

    for handler in after_request_handlers:
        app.after_request(handler)

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    return app
