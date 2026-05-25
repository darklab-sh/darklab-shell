# Contributors

darklab_shell is designed, built, and maintained by [nona](https://github.com/nona).

---

## Contributing

Contributions, bug reports, and feature suggestions are welcome. Before opening a merge request, review the [Contributor Guide](CONTRIBUTING.md) for local setup, coding conventions, tests, and merge request expectations.

Key references for contributors:

- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, branch workflow, code style, linting, and MR process
- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime layers, request flow, persistence model, and security design
- [DECISIONS.md](DECISIONS.md) — design reasoning, known gotchas, and implementation history
- [tests/README.md](tests/README.md) — test suite handbook and full appendix

When adding app-owned shell behavior, keep the browser, backend, autocomplete, and docs in sync. Workspace file commands are a good example: user-visible paths must go through the workspace helpers, browser-side conveniences should have matching backend fallbacks when stale clients are possible, and new terminal grammar should be reflected in `app/services/commands/builtin_autocomplete.yaml`, feature docs, and the test inventory.

---

## Acknowledgements

darklab_shell uses or builds on:

- [Flask](https://flask.palletsprojects.com/) — Python web framework
- [Gunicorn](https://gunicorn.org/) — WSGI HTTP server
- [Redis](https://redis.io/) — shared rate-limit and PID-tracking backend
- [SQLite](https://sqlite.org/) — persistent run history and snapshots
- [PostgreSQL](https://www.postgresql.org/) — optional multi-user database backend
- [psycopg](https://www.psycopg.org/psycopg3/) — PostgreSQL driver and connection pool
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — optional local AI model server
- [ansi_up](https://github.com/drudru/ansi_up) — ANSI-to-HTML rendering
- [jsPDF](https://github.com/parallax/jsPDF) — client-side PDF generation
- [xterm.js](https://github.com/xtermjs/xterm.js) — browser terminal emulator for interactive PTY tabs
- [xterm.js Fit Addon](https://github.com/xtermjs/xterm.js/tree/master/addons/addon-fit) — terminal sizing for interactive PTY tabs
- [pyte](https://pyte.readthedocs.io/) — server-side terminal emulation for saved interactive PTY output
- [prometheus_client](https://github.com/prometheus/client_python) — Prometheus metrics for Python services
- [croniter](https://github.com/kiorky/croniter) — cron schedule parsing
- [cryptography](https://cryptography.io/) — encrypted session secret storage
- [PyYAML](https://pyyaml.org/) — YAML configuration loading
- [psutil](https://github.com/giampaolo/psutil) — process and system metrics
- [JetBrains Mono](https://www.jetbrains.com/lp/mono/) — terminal font
- [Syne](https://www.tunera.xyz/fonts/syne/) — UI heading font
- [SecLists](https://github.com/danielmiessler/SecLists) — wordlist collection included in the container image
- [Flask-Limiter](https://flask-limiter.readthedocs.io/) — rate limiting
- [Playwright](https://playwright.dev/) — browser end-to-end testing
- [Vitest](https://vitest.dev/) — JavaScript unit testing
- [pytest](https://pytest.org/) — Python testing
