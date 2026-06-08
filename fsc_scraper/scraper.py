"""核心抓取與解析：依設定取得資產負債簡表，並解析成 DataFrame。"""

from __future__ import annotations

import io
import logging
import random
import string
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd
from bs4 import BeautifulSoup

from .client import StatisClient
from .config import Config
from .discover import inspect_condition_page, print_condition_page
from .periods import format_roc, parse_period

log = logging.getLogger(__name__)


def _rdm(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_letters, k=n))


@dataclass
class FetchResult:
    df: pd.DataFrame
    start_period: int
    end_period: int
    source_url: str


def detect_latest_period(client: StatisClient, cfg: Config) -> int:
    """從查詢條件頁的期間下拉，推算網站上最新可用的一期。"""
    _, fields = inspect_condition_page(client, cfg.base_url, cfg.funid)
    period_opts = print_condition_page(fields)
    candidates: list[int] = []
    for val, _txt in period_opts:
        try:
            candidates.append(parse_period(val))
        except ValueError:
            continue
    if not candidates:
        raise RuntimeError(
            "無法從查詢條件頁找到期間下拉。請先執行 `inspect --funid <funid>` 檢視頁面結構，"
            "或在 config.yaml 用 end_period 指定一個明確的民國年月。"
        )
    latest = max(candidates)
    log.info("偵測到網站最新期：%s (%d)", format_roc(latest), latest)
    return latest


def build_url_from_sample(sample_url: str, start: int, end: int) -> str:
    """以一條「真實擷取到的下載網址」為樣板，只換掉 ym / ymt（與 rdm 防快取）。

    這是最穩的做法：所有 funid / kind / type / cycle 等參數都沿用你實際查到的網址，
    程式不再自行猜測。樹狀點擊只要在瀏覽器成功一次、把網址貼進設定即可。
    """
    parts = urlparse(sample_url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["ym"] = str(start)
    params["ymt"] = str(end)
    if "rdm" in params:
        params["rdm"] = _rdm()
    new_query = urlencode(params)
    return urlunparse(parts._replace(query=new_query))


def build_result_url(cfg: Config, start: int, end: int) -> str:
    """優先使用設定中貼入的真實下載網址；否則退回參數樣板。"""
    sample = cfg.download_url
    if sample:
        return build_url_from_sample(sample, start, end)
    return cfg.result_url_template.format(
        base_url=cfg.base_url,
        ym=start,
        ymt=end,
        funid=cfg.funid,
        outmode=cfg.outmode,
        rdm=_rdm(),
    )


def parse_result(text: str, content_type: str = "") -> pd.DataFrame:
    """把 stmain.jsp 的回應解析成 DataFrame。

    outmode=0 時是 HTML 表格；其他輸出模式可能是 CSV。兩者都嘗試處理。
    """
    stripped = text.lstrip()
    looks_like_html = stripped.startswith("<") or "<table" in text.lower() or "html" in content_type.lower()

    if looks_like_html:
        # 取頁面中資料量最大的表格（通常就是統計表本身）
        try:
            tables = pd.read_html(io.StringIO(text))
        except ValueError:
            tables = []
        if not tables:
            # 退而求其次，手動找最大的 <table>
            soup = BeautifulSoup(text, "lxml")
            tbls = soup.find_all("table")
            if not tbls:
                raise RuntimeError("回應中找不到任何表格，請用 --debug 保存 HTML 後檢視。")
            biggest = max(tbls, key=lambda t: len(t.find_all("tr")))
            tables = pd.read_html(io.StringIO(str(biggest)))
        df = max(tables, key=lambda d: d.size)
        return _clean_table(df)

    # 視為 CSV
    df = pd.read_csv(io.StringIO(text), dtype=str)
    return _clean_table(df)


def _clean_table(df: pd.DataFrame) -> pd.DataFrame:
    # 攤平多層欄名
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(c) for c in col if str(c) != "nan").strip()
            for col in df.columns
        ]
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df.reset_index(drop=True)


def fetch(client: StatisClient, cfg: Config, start: int, end: int, *, debug: bool = False) -> FetchResult:
    url = build_result_url(cfg, start, end)
    log.info("抓取 %s ~ %s：%s", format_roc(start), format_roc(end), url)
    resp = client.get(url)
    text = client._decode(resp)  # noqa: SLF001 - 內部解碼
    if debug:
        import os
        os.makedirs("debug", exist_ok=True)
        with open(f"debug/result_{start}_{end}.html", "w", encoding="utf-8") as f:
            f.write(text)
    df = parse_result(text, resp.headers.get("Content-Type", ""))
    return FetchResult(df=df, start_period=start, end_period=end, source_url=url)
