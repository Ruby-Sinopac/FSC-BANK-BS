"""把長格式資料匯出成「每家銀行一個工作表、列=統計期、欄=各項目」的 Excel。

貼近使用者既有歷史檔的版面（圖2）：每個分頁一家銀行，第一欄統計期，
其後依官方順序排列各資產負債項目。
"""

from __future__ import annotations

import os
import re

import pandas as pd

from .periods import parse_period


def short_bank_name(full: str) -> str:
    """808 玉山商業銀行 -> 玉山；822 中國信託商業銀行 -> 中國信託；本國銀行 維持原樣。"""
    name = re.sub(r"^\d{3}\s*", "", full).strip()  # 去開頭代碼
    name = re.sub(r"(國際商業銀行|商業銀行|銀行)$", "", name).strip()
    return name or full


def _safe_sheet_name(name: str) -> str:
    # Excel 工作表名稱限制：<=31 字、不可含 : \ / ? * [ ]
    name = re.sub(r"[:\\/?*\[\]]", "", name)
    return name[:31] or "Sheet"


def _ordered_unique(series: pd.Series) -> list:
    """保留出現順序的唯一值（項目沿用官方排列順序）。"""
    return list(dict.fromkeys(series.tolist()))


def export_per_bank(long_df: pd.DataFrame, path: str, *, short_names: bool = True, include_total: bool = False) -> int:
    """把長格式輸出成各銀行分頁 Excel。回傳寫出的分頁數。"""
    if long_df.empty:
        return 0

    df = long_df.copy()
    # 期碼用於列排序
    if "期碼" not in df.columns:
        df["期碼"] = df["統計期"].map(lambda v: _safe_parse(v))

    item_order = _ordered_unique(df["項目"])
    banks = _ordered_unique(df["銀行"])
    if not include_total:
        banks = [b for b in banks if b != "本國銀行"]

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    written = 0
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for bank in banks:
            sub = df[df["銀行"] == bank]
            if sub.empty:
                continue
            wide = sub.pivot_table(
                index=["期碼", "統計期"], columns="項目", values="數值", aggfunc="first"
            )
            # 依官方項目順序排欄、依期碼排列
            cols = [c for c in item_order if c in wide.columns]
            wide = wide[cols]
            wide = wide.sort_index(level="期碼")
            wide = wide.reset_index().drop(columns="期碼").rename(columns={"統計期": "統計期"})
            sheet = _safe_sheet_name(short_bank_name(bank) if short_names else bank)
            wide.to_excel(writer, sheet_name=sheet, index=False)
            written += 1
    return written


def _safe_parse(v) -> int:
    try:
        return parse_period(v)
    except ValueError:
        return -1
