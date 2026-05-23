"""HTTP Basic Auth middleware.

The operator console is single-user (one operator per deployment, or
a tight team sharing one credential). Basic auth + HTTPS in front of
uvicorn is the right cost/security tradeoff. When this grows to
multi-operator with audit, swap in OAuth/JWT.

The middleware compares credentials in constant time so the response
time can't be used to enumerate the password byte-by-byte.
"""
from __future__ import annotations

import base64
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_REALM = 'parts-pipeline'


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, username: str, password: str, public_paths=()):
        super().__init__(app)
        self._user_b = username.encode("utf-8")
        self._pass_b = password.encode("utf-8")
        self._public = tuple(public_paths)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p) for p in self._public):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("basic "):
            return self._challenge()

        try:
            raw = base64.b64decode(header.split(" ", 1)[1].encode("ascii"))
        except Exception:
            return self._challenge()

        if b":" not in raw:
            return self._challenge()
        user, _, pwd = raw.partition(b":")

        # Constant-time comparison on each half.
        ok_user = hmac.compare_digest(user, self._user_b)
        ok_pass = hmac.compare_digest(pwd, self._pass_b)
        if not (ok_user and ok_pass):
            return self._challenge()

        return await call_next(request)

    @staticmethod
    def _challenge() -> Response:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{_REALM}"'},
            content="Authentication required.",
            media_type="text/plain",
        )
