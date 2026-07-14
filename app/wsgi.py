# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""WSGI entrypoint for production and browser-test servers."""

from runtime_bootstrap import bootstrap

application = bootstrap()
