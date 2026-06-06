"""歷史資料檔讀寫與增量合併。支援 .xlsx 與 .csv。"""

from __future__ import annotations

import os

import pandas as pd

from .periods import parse_period


def load_existing(path: str, sheet_name: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    if path.lower().endswith(".csv"):
        return pd.read_csv(path, dtype=str)
    return pd.read_excel(path, sheet_name=sheet_name, dtype=str)


def latest_period_in(df: pd.DataFrame | None, period_column: str) -> int | None:
    """回傳歷史資料中最大的期間碼；找不到欄位或無資料時回 None。"""
    if df is None or df.empty or period_column not in df.columns:
        return None
    periods = []
    for v in df[period_column].dropna():
        try:
            periods.append(parse_period(v))
        except ValueError:
            continue
    return max(periods) if periods else None


def merge(existing: pd.DataFrame | None, new: pd.DataFrame, period_column: str) -> pd.DataFrame:
    """合併新舊資料；以 period_column 去重（新資料優先），並依期間排序。"""
    if existing is None or existing.empty:
        combined = new.copy()
    else:
        combined = pd.concat([existing, new], ignore_index=True)

    if period_column in combined.columns:
        # 後出現者（new）優先 -> keep="last"
        combined = combined.drop_duplicates(subset=[period_column], keep="last")
        combined["_sort"] = combined[period_column].map(
            lambda v: _safe_parse(v)
        )
        combined = combined.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
    return combined


def _safe_parse(v) -> int:
    try:
        return parse_period(v)
    except ValueError:
        return -1


def save(df: pd.DataFrame, path: str, sheet_name: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if path.lower().endswith(".csv"):
        df.to_csv(path, index=False, encoding="utf-8-sig")  # utf-8-sig 讓 Excel 開不亂碼
    else:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
