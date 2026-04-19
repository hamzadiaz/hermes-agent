"""httpx-compatible transport backed by curl_cffi for TLS fingerprint impersonation.

Used by the openai-codex provider to bypass Cloudflare bot detection on
chatgpt.com/backend-api/codex — Python httpx triggers CF's JA3/JA4 checks,
but curl_cffi can impersonate Chrome's TLS fingerprint which CF trusts.
"""

from __future__ import annotations

from typing import Iterator

import httpx


class _CurlSyncStream(httpx.SyncByteStream):
    """Adapts a curl_cffi streaming response to httpx's SyncByteStream interface."""

    def __init__(self, curl_response) -> None:
        self._response = curl_response

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._response.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    def close(self) -> None:
        try:
            self._response.close()
        except Exception:
            pass


class CurlCffiTransport(httpx.BaseTransport):
    """Synchronous httpx transport that uses curl_cffi for TLS impersonation.

    Pass an instance to httpx.Client(transport=...) which is then given to
    openai.OpenAI(http_client=...) so all SDK requests go through curl_cffi.
    """

    def __init__(self, impersonate: str = "chrome131") -> None:
        self._impersonate = impersonate
        self._session = None

    def _get_session(self):
        if self._session is None:
            from curl_cffi import requests as cr
            self._session = cr.Session(impersonate=self._impersonate)
        return self._session

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        session = self._get_session()
        headers = dict(request.headers)
        resp = session.request(
            method=request.method,
            url=str(request.url),
            headers=headers,
            data=request.content,
            stream=True,
        )
        return httpx.Response(
            status_code=resp.status_code,
            headers=list(resp.headers.items()),
            stream=_CurlSyncStream(resp),
            request=request,
        )

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
