"""探查工具：協助找出「資產負債簡表(102年以後)」的 funid，以及查詢條件頁的欄位/期間。

因為這類政府統計系統的左側樹狀選單與查詢條件頁，常因改版而參數略有不同，
這支工具的目的是「把網站實際長相 dump 出來」，讓你（或我）據此正確設定 config.yaml。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .client import StatisClient


@dataclass
class MenuNode:
    text: str
    funid: str
    href: str
    params: dict[str, str]


# 樹狀選單節點通常連到「查詢條件設定」頁（webMain.aspx?...funid=iXXXXX）
_FUNID_RE = re.compile(r"funid=([A-Za-z0-9_]+)", re.IGNORECASE)


def _extract_nodes(html: str, base_url: str) -> list[MenuNode]:
    soup = BeautifulSoup(html, "lxml")
    nodes: list[MenuNode] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        m = _FUNID_RE.search(href)
        if not m:
            continue
        full = urljoin(base_url + "/", href)
        qs = parse_qs(urlparse(full).query)
        nodes.append(
            MenuNode(
                text=a.get_text(strip=True),
                funid=m.group(1),
                href=full,
                params={k: v[0] for k, v in qs.items()},
            )
        )
    return nodes


def discover_menu(client: StatisClient, base_url: str, keyword: str = "資產負債簡表") -> list[MenuNode]:
    """抓「網站導覽 (allmenu)」與「自選統計項查詢 (defqry)」，回傳所有節點。

    會把含 keyword 的節點特別標示，方便找出目標表的 funid。
    """
    all_nodes: dict[str, MenuNode] = {}
    for funid in ("allmenu", "defqry", "defqry2", "menurel"):
        url = f"{base_url}/webMain.aspx?sys=100&funid={funid}"
        try:
            html = client.get_text(url)
        except Exception as exc:  # noqa: BLE001 - 探查階段盡量不要中斷
            print(f"  (略過 {funid}：{exc})")
            continue
        for node in _extract_nodes(html, base_url):
            # 以 funid 去重；保留有文字描述的版本
            if node.funid not in all_nodes or (node.text and not all_nodes[node.funid].text):
                all_nodes[node.funid] = node
    return list(all_nodes.values())


def print_menu(nodes: list[MenuNode], keyword: str = "資產負債簡表") -> None:
    matches = [n for n in nodes if keyword in n.text]
    print(f"\n找到 {len(nodes)} 個節點，其中 {len(matches)} 個含「{keyword}」：\n")
    if matches:
        print("=== 符合關鍵字的節點（請從中挑出『(102年以後)』那一張，把 funid 填入 config.yaml）===")
        for n in matches:
            print(f"  funid={n.funid:<10} {n.text}")
            print(f"      {n.href}")
    else:
        print("(沒有節點文字含關鍵字；可能選單是用 JavaScript/postback 動態載入。")
        print(" 請改用 inspect 直接針對已知 funid dump，或把下方完整清單貼給我。)")
    print("\n=== 全部節點（前 200 筆）===")
    for n in nodes[:200]:
        print(f"  funid={n.funid:<10} {n.text}")


# --------------------------------------------------------------------------
# 查詢條件頁的欄位/期間 dump
# --------------------------------------------------------------------------
@dataclass
class FormField:
    tag: str
    name: str
    value: str
    options: list[tuple[str, str]]  # (value, text)


def inspect_condition_page(client: StatisClient, base_url: str, funid: str) -> tuple[str, list[FormField]]:
    """抓某 funid 的查詢條件設定頁，回傳 (原始HTML, 表單欄位清單)。"""
    # 條件頁常見於 sys=210；若不同系統可自行調整。
    url = f"{base_url}/webMain.aspx?sys=210&kind=21&type=1&funid={funid}"
    html = client.get_text(url)
    soup = BeautifulSoup(html, "lxml")
    fields: list[FormField] = []

    for inp in soup.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        fields.append(FormField("input", name, inp.get("value", ""), []))

    for sel in soup.find_all("select"):
        name = sel.get("name") or sel.get("id") or "(無名稱)"
        options = [(o.get("value", ""), o.get_text(strip=True)) for o in sel.find_all("option")]
        selected = next((o.get("value", "") for o in sel.find_all("option") if o.get("selected")), "")
        fields.append(FormField("select", name, selected, options))

    return html, fields


def print_condition_page(fields: list[FormField]) -> list[tuple[str, str]]:
    """印出表單欄位，並嘗試找出「期間/統計期」下拉，回傳其 options（供推算最新期）。"""
    print("\n=== 查詢條件頁表單欄位 ===")
    period_options: list[tuple[str, str]] = []
    for f in fields:
        if f.tag == "input":
            shown = f.value if len(f.value) < 60 else f.value[:57] + "..."
            print(f"  [input ] {f.name} = {shown!r}")
        else:
            print(f"  [select] {f.name}  (預設={f.value!r}, {len(f.options)} 個選項)")
            for val, txt in f.options[:6]:
                print(f"             {val!r} -> {txt}")
            if len(f.options) > 6:
                print(f"             ... 其餘 {len(f.options) - 6} 個")
            # 判斷是否為期間下拉：選項值多為 5 碼數字（民國yyymm）
            digit_opts = [(v, t) for v, t in f.options if re.fullmatch(r"\d{4,6}", v or "")]
            if len(digit_opts) > len(period_options):
                period_options = digit_opts
    return period_options


def save_debug_html(html: str, name: str) -> str:
    os.makedirs("debug", exist_ok=True)
    path = os.path.join("debug", name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
