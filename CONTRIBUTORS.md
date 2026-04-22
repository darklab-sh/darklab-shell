# Contributors

darklab shell is designed, built, and maintained by [nona](https://github.com/nona).

---

## Contributing

Contributions, bug reports, and feature suggestions are welcome. Before submitting a merge request, review the [Contributor Guide](CONTRIBUTING.md) for local setup, coding conventions, the test workflow, and merge request expectations.

Key references for contributors:

- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, branch workflow, code style, linting, and MR process
- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime layers, request flow, persistence model, and security design
- [DECISIONS.md](DECISIONS.md) — architectural rationale, known gotchas, and implementation history
- [tests/README.md](tests/README.md) — test suite handbook and full appendix

Current implementation note:

- The desktop rail is the visible desktop navigation surface, but some rail actions still proxy through legacy hidden header button IDs so older controller wiring can be reused. That desktop-only indirection is tracked as technical debt in [TODO.md](TODO.md).
- Export/render de-duplication is the other active frontend debt area: live permalink/share pages and saved HTML/PDF exports already share most rendering helpers, but bootstrap/header/transcript normalization is not fully unified yet. That broader cleanup plan is also tracked in [TODO.md](TODO.md).

---

## Acknowledgements

darklab shell uses or builds on:

- [Flask](https://flask.palletsprojects.com/) — Python web framework
- [Gunicorn](https://gunicorn.org/) — WSGI HTTP server
- [Redis](https://redis.io/) — shared rate-limit and PID-tracking backend
- [SQLite](https://sqlite.org/) — persistent run history and snapshots
- [ansi_up](https://github.com/drudru/ansi_up) — ANSI-to-HTML rendering
- [jsPDF](https://github.com/parallax/jsPDF) — client-side PDF generation
- [JetBrains Mono](https://www.jetbrains.com/lp/mono/) — terminal font
- [Syne](https://www.tunera.xyz/fonts/syne/) — UI heading font
- [SecLists](https://github.com/danielmiessler/SecLists) — wordlist collection included in the container image
- [Flask-Limiter](https://flask-limiter.readthedocs.io/) — rate limiting
- [Playwright](https://playwright.dev/) — browser end-to-end testing
- [Vitest](https://vitest.dev/) — JavaScript unit testing
- [pytest](https://pytest.org/) — Python testing
