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
    def result_url_template(self) -> str:
        return self.raw["query"]["result_url_template"]

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
    def http(self) -> dict[str, Any]:
        return self.raw.get("http", {})


def load_config(path: str | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到設定檔：{path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    # 基本驗證
    for section in ("site", "query", "storage"):
        if section not in raw:
            raise ValueError(f"設定檔缺少區段：{section}")
    return Config(raw=raw)
