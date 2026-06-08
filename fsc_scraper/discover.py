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


# 樹狀選單節點通常連到「查詢條件設定」頁（webMain.aspx?...funid=iXXXXX）。
# funid 可能出現在 <a href>、onclick、或內嵌 JavaScript 的字串中，這裡一律掃出來。
_FUNID_RE = re.compile(r"funid=([A-Za-z0-9_]+)", re.IGNORECASE)
# 連 funid 一起的整段網址（用來在純 JS 樹中還原連結）
_URL_RE = re.compile(r"""[\w./?=&%-]*funid=[A-Za-z0-9_]+[\w./?=&%-]*""", re.IGNORECASE)


def _node_from_url(fragment: str, text: str, base_url: str) -> MenuNode | None:
    m = _FUNID_RE.search(fragment)
    if not m:
        return None
    full = urljoin(base_url + "/", fragment.lstrip("./"))
    qs = parse_qs(urlparse(full).query)
    return MenuNode(
        text=text,
        funid=m.group(1),
        href=full,
        params={k: v[0] for k, v in qs.items()},
    )


def _extract_nodes(html: str, base_url: str) -> list[MenuNode]:
    """從一頁 HTML 盡量挖出所有帶 funid 的節點：
    1) <a href> / onclick 屬性
    2) 內嵌 <script> 或任何文字中出現的 funid=... 字串（純 JS 樹常見）
    """
    soup = BeautifulSoup(html, "lxml")
    nodes: list[MenuNode] = []

    for a in soup.find_all("a"):
        for attr in ("href", "onclick"):
            val = (a.get(attr) or "").strip()
            if "funid=" in val.lower():
                node = _node_from_url(val, a.get_text(strip=True), base_url)
                if node:
                    nodes.append(node)
                break

    # 退而求其次：掃整頁文字裡的 funid 網址（抓不到文字描述時 text 會留空）
    if not nodes:
        for frag in set(_URL_RE.findall(html)):
            node = _node_from_url(frag, "", base_url)
            if node:
                nodes.append(node)

    return nodes


def _follow_frames(html: str, base_url: str) -> list[str]:
    """回傳頁面中 frame / iframe 的 src（絕對網址）。"""
    soup = BeautifulSoup(html, "lxml")
    srcs = []
    for tag in soup.find_all(["frame", "iframe"]):
        src = (tag.get("src") or "").strip()
        if src:
            srcs.append(urljoin(base_url + "/", src))
    return srcs


def discover_menu(
    client: StatisClient,
    base_url: str,
    keyword: str = "資產負債簡表",
    *,
    debug: bool = False,
) -> list[MenuNode]:
    """抓選單相關頁面（含其 frame/iframe），回傳所有帶 funid 的節點。

    debug=True 時會把每一頁原始 HTML 存到 debug/，方便診斷「找到 0 個節點」的情況。
    """
    # 先訪問首頁以取得 ASP.NET 會話 cookie，有些頁面沒有 cookie 會回空白。
    try:
        client.get_text(f"{base_url}/webMain.aspx?sys=100&funid=defqry")
    except Exception:  # noqa: BLE001
        pass

    all_nodes: dict[str, MenuNode] = {}
    to_visit = [f"{base_url}/webMain.aspx?sys=100&funid={f}" for f in ("allmenu", "defqry", "defqry2", "menurel")]
    visited: set[str] = set()

    while to_visit:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            html = client.get_text(url)
        except Exception as exc:  # noqa: BLE001 - 探查階段盡量不要中斷
            print(f"  (略過 {url}：{exc})")
            continue

        if debug:
            fname = re.sub(r"[^\w]+", "_", url.split("/statis/")[-1])[:80] + ".html"
            print(f"  抓到 {url} （{len(html)} 字元）-> debug/{fname}")
            save_debug_html(html, fname)

        for node in _extract_nodes(html, base_url):
            if node.funid not in all_nodes or (node.text and not all_nodes[node.funid].text):
                all_nodes[node.funid] = node

        # 跟著 frame/iframe 再抓一層（樹狀選單常放在獨立 frame 裡）
        for frame_url in _follow_frames(html, base_url):
            if frame_url not in visited:
                to_visit.append(frame_url)

    return list(all_nodes.values())


def print_menu(nodes: list[MenuNode], keyword: str = "資產負債簡表") -> None:
    matches = [n for n in nodes if keyword in n.text]
    print(f"\n找到 {len(nodes)} 個節點，其中 {len(matches)} 個含「{keyword}」：\n")
    if matches:
        print("=== 符合關鍵字的節點（請從中挑出『(102年以後)』那一張，把 funid 填入 config.yaml）===")
        for n in matches:
            print(f"  funid={n.funid:<10} {n.text}")
            print(f"      {n.href}")
    elif nodes:
        print(f"(抓到節點但沒有文字含「{keyword}」；可能描述文字在別處。下方列出全部 funid 供比對。)")
    else:
        print("找到 0 個節點。這個樹狀選單很可能是用 JavaScript 動態展開、不是普通連結，所以抓不到。")
        print("建議改用「瀏覽器手動取得網址」的方式：")
        print("  1. 瀏覽器開 webMain.aspx?sys=100&funid=defqry，點開左側樹找到目標表並查詢")
        print("  2. 把結果頁網址列那串(含 funid=、ym=)複製給我即可")
        print("或加上 --debug 重跑，會把原始網頁存到 debug/，把檔案內容貼給我我幫你定位。")
    if nodes:
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
