"""HTTP client：瀏覽器標頭、重試（指數退避）、自動編碼偵測。

這個 statis 系統對沒有瀏覽器標頭的請求可能回 403，因此一律帶上常見標頭，
並維持同一個 session 以保留 cookie（ASP.NET 會話）。
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)


class StatisClient:
    def __init__(
        self,
        user_agent: str,
        timeout: int = 60,
        retries: int = 4,
        delay: float = 1.5,
        encoding: str = "auto",
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self.encoding = encoding
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
            }
        )

    # -- 編碼處理 --------------------------------------------------------
    def _decode(self, resp: requests.Response) -> str:
        if self.encoding and self.encoding != "auto":
            resp.encoding = self.encoding
            return resp.text
        # 自動：先信任 HTTP 標頭，否則用 requests 的猜測（chardet/charset-normalizer）。
        if resp.encoding and resp.encoding.lower() not in ("iso-8859-1",):
            return resp.text
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    # -- 請求 ------------------------------------------------------------
    def get(self, url: str, *, referer: str | None = None) -> requests.Response:
        headers = {"Referer": referer} if referer else {}
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                if self.delay:
                    time.sleep(self.delay)
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning("GET 失敗 (第 %d/%d 次)：%s；%ds 後重試", attempt, self.retries, exc, wait)
                time.sleep(wait)
        raise RuntimeError(f"GET 連續失敗：{url}") from last_exc

    def get_text(self, url: str, *, referer: str | None = None) -> str:
        return self._decode(self.get(url, referer=referer))

    def post(self, url: str, data: dict, *, referer: str | None = None) -> requests.Response:
        headers = {"Referer": referer} if referer else {}
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.post(url, data=data, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                if self.delay:
                    time.sleep(self.delay)
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning("POST 失敗 (第 %d/%d 次)：%s；%ds 後重試", attempt, self.retries, exc, wait)
                time.sleep(wait)
        raise RuntimeError(f"POST 連續失敗：{url}") from last_exc

    def post_text(self, url: str, data: dict, *, referer: str | None = None) -> str:
        return self._decode(self.post(url, data, referer=referer))
