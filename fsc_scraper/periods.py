"""民國年月（ROC year-month）期間處理工具。

本系統的期間參數（ym / ymt）格式為「民國年(3碼) + 月(2碼)」整數，例如：
    民國102年1月  -> 10201
    民國114年12月 -> 11412
本模組以 int 表示一個期間碼，並提供 +1 月、解析、格式化等運算。
"""

from __future__ import annotations

import re


def parse_period(value) -> int:
    """把各種寫法的期間轉成整數期間碼（民國yyymm）。

    接受：10201、"10201"、"102/01"、"102年01月"、"102.1" 等。
    """
    if value is None:
        raise ValueError("期間不可為空")
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    # 抽出數字群組：年、月
    nums = re.findall(r"\d+", s)
    if len(nums) >= 2:
        year, month = int(nums[0]), int(nums[1])
        return year * 100 + month
    raise ValueError(f"無法解析期間：{value!r}")


def format_roc(period: int) -> str:
    """10201 -> '102年01月'。"""
    year, month = divmod(period, 100)
    return f"{year}年{month:02d}月"


def next_month(period: int) -> int:
    """回傳下一個月的期間碼。10212 -> 10301。"""
    year, month = divmod(period, 100)
    if month >= 12:
        return (year + 1) * 100 + 1
    return year * 100 + (month + 1)


def iter_months(start: int, end: int):
    """產生 start..end（含）之間每個月的期間碼。"""
    cur = start
    while cur <= end:
        yield cur
        cur = next_month(cur)


def current_roc_period() -> int:
    """以系統當下日期回傳當月的民國年月碼，作為「最新期」的上界。

    例如西元 2026-06 -> 民國115年6月 -> 11506。
    （資料通常有發布時差，抓到當月只是上界，系統會回傳實際已公布的最新期。）
    """
    import datetime as _dt

    today = _dt.date.today()
    return (today.year - 1911) * 100 + today.month
