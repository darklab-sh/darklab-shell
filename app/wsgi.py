"""WSGI entrypoint for production and browser-test servers."""

from runtime_bootstrap import bootstrap

application = bootstrap()
