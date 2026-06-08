"""核心抓取與解析：依設定取得資產負債簡表，並解析成 DataFrame。"""

from __future__ import annotations

import io
import logging
import random
import re
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
    # 保留逗號為字面值（fldspc/codspc0 用逗號分隔，原始網址即為字面逗號），
    # 避免被編成 %2C 後讓挑剔的舊系統解析失敗。
    new_query = urlencode(params, safe=",")
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


_PERIOD_PAT = re.compile(r"\d{2,3}\s*年|\d{3,4}/\d{1,2}|\d{5,6}")
_NUMERIC_PAT = re.compile(r"\d{1,3}(,\d{3})+|\d+\.\d+")
_BOILERPLATE = ("產生時間", "點選結果表", "單位：", "單位:", "回上頁", "列印", "查詢條件")


def _table_score(df: pd.DataFrame) -> float:
    """替一個候選表格評分：含『年月』期別、數字越多越像資料表；樣板字越多越扣分。"""
    text = " ".join(str(v) for v in df.to_numpy().ravel()[:2000])
    score = 0.0
    score += 30 * len(_PERIOD_PAT.findall(text))
    score += len(_NUMERIC_PAT.findall(text))
    score += 0.1 * df.size
    for bad in _BOILERPLATE:
        score -= 20 * text.count(bad)
    return score


def _leaf_tables_html(text: str) -> list[str]:
    """回傳所有「最內層」(不再包含子表格) 的 <table> HTML 字串。"""
    soup = BeautifulSoup(text, "lxml")
    leaves = [t for t in soup.find_all("table") if not t.find("table")]
    return [str(t) for t in leaves]


def parse_result(text: str, content_type: str = "") -> pd.DataFrame:
    """把結果頁解析成 DataFrame。

    這個 statis 系統是「表格包表格」，真正的資料在最內層表格，且外層常是
    產生時間/單位/點選提示等樣板。因此優先在「最內層表格」中挑分數最高者。
    outmode 若為 CSV 也一併處理。
    """
    stripped = text.lstrip()
    looks_like_html = stripped.startswith("<") or "<table" in text.lower() or "html" in content_type.lower()

    if looks_like_html:
        candidates: list[pd.DataFrame] = []
        # 1) 先試最內層表格（最可能是純資料）
        for html in _leaf_tables_html(text):
            try:
                candidates.extend(pd.read_html(io.StringIO(html)))
            except ValueError:
                continue
        # 2) 退而求其次：整頁所有表格
        if not candidates:
            try:
                candidates = pd.read_html(io.StringIO(text))
            except ValueError:
                candidates = []
        if not candidates:
            raise RuntimeError("回應中找不到任何資料表格，請用 --debug 保存 HTML 後用 analyze 檢視。")
        df = max(candidates, key=_table_score)
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


# 欄名攤平後形如「<項目> <銀行>」，銀行為結尾的「NNN 某某銀行」或「本國銀行」。
_BANK_TAIL = re.compile(r"\s*(\d{3}\s*\S+|本國銀行)$")
# 純期別字串（如「115年 2月」）
_PERIOD_ONLY = re.compile(r"^\D*\d{2,3}\s*年")


def _split_item_bank(col: str) -> tuple[str, str] | None:
    """把攤平欄名拆成 (項目, 銀行)。拆不出銀行則回 None（多半是期別欄）。"""
    col = col.strip()
    m = _BANK_TAIL.search(col)
    if not m:
        return None
    bank = m.group(1).strip()
    item = col[: m.start()].strip()
    if not item:
        return None
    return item, bank


# 各項目表的第一欄欄名常是「本國銀行－資產負債簡表 &nbsp;&nbsp;」之類，視為期別欄。
LONG_COLUMNS = ["統計期", "期碼", "銀行", "項目", "數值"]


def parse_balance_sheet(text: str) -> pd.DataFrame:
    """把一頁結果（內含每個項目一張小表）攤平成長格式 DataFrame。

    回傳欄位：統計期(顯示字串)、期碼(int, 民國yyymm)、銀行、項目、數值。
    """
    records: list[tuple] = []
    for html in _leaf_tables_html(text):
        try:
            dfs = pd.read_html(io.StringIO(html))
        except ValueError:
            continue
        for raw in dfs:
            df = _clean_table(raw)
            if df.shape[1] < 2 or df.empty:
                continue
            period_col = df.columns[0]
            # 確認第一欄真的是期別
            if not df[period_col].astype(str).str.contains(r"\d{2,3}\s*年").any():
                continue
            # 找出各資料欄的 (項目, 銀行)
            data_cols = {c: _split_item_bank(c) for c in df.columns[1:]}
            data_cols = {c: ib for c, ib in data_cols.items() if ib}
            if not data_cols:
                continue
            for _, row in df.iterrows():
                raw_period = str(row[period_col]).strip()
                if not _PERIOD_ONLY.search(raw_period):
                    continue
                try:
                    code = parse_period(raw_period)
                except ValueError:
                    continue
                period_disp = format_roc(code)  # 統一成「115年02月」
                for col, (item, bank) in data_cols.items():
                    val = row[col]
                    if pd.isna(val):
                        continue
                    records.append((period_disp, code, bank, item, val))

    long = pd.DataFrame.from_records(records, columns=LONG_COLUMNS)
    if not long.empty:
        long = long.drop_duplicates(subset=["期碼", "銀行", "項目"], keep="last").reset_index(drop=True)
    return long


def _fetch_one(client: StatisClient, url: str, start: int, end: int, *, tag: str = "", debug: bool = False) -> pd.DataFrame:
    log.info("抓取 %s ~ %s：%s", format_roc(start), format_roc(end), url)
    resp = client.get(url)
    text = client._decode(resp)  # noqa: SLF001 - 內部解碼
    if debug:
        import os
        os.makedirs("debug", exist_ok=True)
        fname = f"debug/result_{start}_{end}{('_' + tag) if tag else ''}.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(text)
    return parse_balance_sheet(text)


def fetch(client: StatisClient, cfg: Config, start: int, end: int, *, debug: bool = False) -> FetchResult:
    """抓取所有 download_urls（各自替換 ym/ymt），解析成長格式後合併。"""
    urls = cfg.download_urls or [build_result_url(cfg, start, end)]
    frames: list[pd.DataFrame] = []
    for i, sample in enumerate(urls, 1):
        url = build_url_from_sample(sample, start, end) if cfg.download_urls else sample
        df = _fetch_one(client, url, start, end, tag=str(i), debug=debug)
        frames.append(df)
        log.info("第 %d/%d 條網址：解析出 %d 筆", i, len(urls), len(df))
    combined = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    if not combined.empty:
        combined = combined.drop_duplicates(subset=["期碼", "銀行", "項目"], keep="last").reset_index(drop=True)
    return FetchResult(df=combined, start_period=start, end_period=end, source_url=" ; ".join(urls))
