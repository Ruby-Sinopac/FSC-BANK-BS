"""讀取並驗證 config.yaml。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"
)


@dataclass
class Config:
    raw: dict[str, Any] = field(default_factory=dict)

    # --- 方便存取的捷徑 ---
    @property
    def base_url(self) -> str:
        return self.raw["site"]["base_url"].rstrip("/")

    @property
    def encoding(self) -> str:
        return self.raw["site"].get("encoding", "auto")

    @property
    def funid(self) -> str:
        return (self.raw["query"].get("funid") or "").strip()

    @property
    def download_url(self) -> str:
        """從瀏覽器/錄製擷取到的完整下載網址（含 ym/ymt）。設了就優先用它。"""
        return (self.raw["query"].get("download_url") or "").strip()

    @property
    def download_urls(self) -> list[str]:
        """一或多條完整下載網址（含 ym/ymt）。多條會分別抓取再合併。

        相容單條 download_url：若只填了 download_url 也會被納入。
        """
        urls = self.raw["query"].get("download_urls") or []
        if isinstance(urls, str):
            urls = [urls]
        urls = [u.strip() for u in urls if u and u.strip()]
        single = self.download_url
        if single and single not in urls:
            urls.insert(0, single)
        return urls

    @property
    def result_url_template(self) -> str:
        return self.raw["query"].get("result_url_template", "")

    @property
    def outmode(self) -> int:
        return int(self.raw["query"].get("outmode", 0))

    @property
    def start_period(self) -> str:
        return str(self.raw["query"].get("start_period", "auto"))

    @property
    def end_period(self) -> str:
        return str(self.raw["query"].get("end_period", "latest"))

    @property
    def data_file(self) -> str:
        return self.raw["storage"]["data_file"]

    @property
    def sheet_name(self) -> str:
        return self.raw["storage"].get("sheet_name", "Sheet1")

    @property
    def period_column(self) -> str:
        return self.raw["storage"].get("period_column", "期間")

    @property
    def key_columns(self) -> list[str]:
        """合併去重用的鍵欄位。多家銀行時通常是 [期別, 銀行]。

        未設定時退回 [period_column]。
        """
        keys = self.raw["storage"].get("key_columns")
        if keys:
            return [str(k) for k in keys]
        return [self.period_column]

    # --- 匯出（各銀行分頁 Excel）---
    @property
    def export(self) -> dict[str, Any]:
        return self.raw.get("export", {})

    @property
    def export_enabled(self) -> bool:
        return bool(self.export.get("enabled", False))

    @property
    def export_file(self) -> str:
        return self.export.get("file", "data/per_bank.xlsx")

    @property
    def short_sheet_names(self) -> bool:
        return bool(self.export.get("short_sheet_names", True))

    @property
    def include_total(self) -> bool:
        return bool(self.export.get("include_total", False))

    # --- 直接更新進既有 Excel ---
    @property
    def excel_target(self) -> dict[str, Any]:
        return self.raw.get("excel_target", {})

    @property
    def excel_target_enabled(self) -> bool:
        return bool(self.excel_target.get("enabled", False))

    @property
    def excel_target_file(self) -> str:
        return self.excel_target.get("file", "")

    @property
    def excel_target_backup(self) -> bool:
        return bool(self.excel_target.get("backup", True))

    @property
    def excel_target_backup_dir(self) -> str:
        """備份存放資料夾；留空 = 執行程式的資料夾(目前工作目錄)。"""
        return (self.excel_target.get("backup_dir") or "").strip()

    @property
    def http(self) -> dict[str, Any]:
        return self.raw.get("http", {})

    @property
    def verify_ssl(self) -> bool:
        return bool(self.raw.get("http", {}).get("verify_ssl", True))


def load_config(path: str | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到設定檔：{path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        hint = ""
        if "double-quoted" in str(exc) or "\\" in text:
            hint = (
                "\n\n常見原因：把含反斜線 \\ 的 Windows 路徑放進「雙引號」了。\n"
                "請改成下列任一種：\n"
                "  1) 只寫檔名（Excel 放在同資料夾）：  file: \"檔名.xlsx\"\n"
                "  2) 用單引號包路徑：                  file: 'Z:\\資料夾\\檔名.xlsx'\n"
                "  3) 路徑改用正斜線：                  file: \"Z:/資料夾/檔名.xlsx\""
            )
        raise ValueError(f"config.yaml 格式有誤（YAML 解析失敗）：{exc}{hint}") from None
    # 基本驗證
    for section in ("site", "query", "storage"):
        if section not in raw:
            raise ValueError(f"設定檔缺少區段：{section}")
    return Config(raw=raw)
