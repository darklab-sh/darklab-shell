# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Test-only HTTPS OIDC provider mounted beside the isolated Playwright app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from threading import Lock

from joserfc import jwk, jwt
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Request, Response

from runtime_bootstrap import bootstrap

ISSUER = os.environ["OIDC_ISSUER"]
CLIENT_ID = os.environ["OIDC_CLIENT_ID"]
CLIENT_SECRET = os.environ["OIDC_CLIENT_SECRET"]
REDIRECT_URI = os.environ["OIDC_REDIRECT_URI"]
_KEY = jwk.RSAKey.generate_key(2048, private=True)
_CODES: dict[str, tuple[str, str, str]] = {}
_LOCK = Lock()


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _error(message: str, status: int = 400) -> Response:
    return Response(message, status=status, content_type="text/plain")


def _json(payload: dict) -> Response:
    return Response(json.dumps(payload), mimetype="application/json")


@Request.application
def provider(request: Request) -> Response:
    if request.path == "/.well-known/openid-configuration":
        return _json({
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/jwks",
            "code_challenge_methods_supported": ["S256"],
        })
    if request.path == "/jwks":
        return _json({"keys": [_KEY.as_dict(private=False)]})
    if request.path == "/authorize" and request.method == "GET":
        query = request.args
        if (query.get("response_type") != "code" or query.get("client_id") != CLIENT_ID
                or query.get("redirect_uri") != REDIRECT_URI or query.get("code_challenge_method") != "S256"
                or not query.get("state") or not query.get("nonce") or not query.get("code_challenge")):
            return _error("invalid authorization request")
        code = secrets.token_urlsafe(32)
        with _LOCK:
            _CODES[code] = (query["code_challenge"], query["nonce"], query["redirect_uri"])
        return Response(status=302, headers={"Location": f"{REDIRECT_URI}?code={code}&state={query['state']}"})
    if request.path == "/token" and request.method == "POST":
        try:
            scheme, encoded = request.headers.get("Authorization", "").split(" ", 1)
            client, secret = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return _error("invalid client", 401)
        if (scheme != "Basic" or not hmac.compare_digest(client, CLIENT_ID)
                or not hmac.compare_digest(secret, CLIENT_SECRET)
                or request.form.get("grant_type") != "authorization_code"):
            return _error("invalid client", 401)
        code = request.form.get("code", "")
        with _LOCK:
            flow = _CODES.pop(code, None)
        verifier = request.form.get("code_verifier", "")
        if (not flow or request.form.get("redirect_uri") != flow[2]
                or not hmac.compare_digest(_challenge(verifier), flow[0])):
            return _error("invalid code")
        now = int(time.time())
        id_token = jwt.encode({"alg": "RS256"}, {
            "iss": ISSUER, "sub": "playwright-subject", "aud": CLIENT_ID,
            "exp": now + 300, "iat": now, "auth_time": now, "nonce": flow[1],
        }, _KEY)
        return _json({
            "access_token": secrets.token_urlsafe(24), "token_type": "Bearer",
            "expires_in": 300, "id_token": id_token,
        })
    return _error("not found", 404)


application = DispatcherMiddleware(bootstrap(), {"/idp": provider})
