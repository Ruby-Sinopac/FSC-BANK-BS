"""命令列入口： python -m fsc_scraper <command>

指令：
  discover-menu   抓網站導覽，列出所有節點與 funid，找出「資產負債簡表(102年以後)」
  inspect         dump 某 funid 的查詢條件頁（表單欄位、可選期間、範例網址）
  update          依 config.yaml 抓最新資料並增量合併到歷史檔
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import storage
from .client import StatisClient
from .config import load_config
from .discover import (
    discover_menu,
    inspect_condition_page,
    print_condition_page,
    print_menu,
    save_debug_html,
)
from .periods import current_roc_period, format_roc, next_month, parse_period
from .scraper import build_result_url, detect_latest_period, fetch


def _make_client(cfg) -> StatisClient:
    http = cfg.http
    return StatisClient(
        user_agent=http.get("user_agent", "Mozilla/5.0"),
        timeout=int(http.get("timeout", 60)),
        retries=int(http.get("retries", 4)),
        delay=float(http.get("delay_between_requests", 1.5)),
        encoding=cfg.encoding,
        verify_ssl=cfg.verify_ssl,
    )


def cmd_discover_menu(cfg, args) -> int:
    client = _make_client(cfg)
    print(f"正在抓取網站導覽 ({cfg.base_url}) …")
    nodes = discover_menu(client, cfg.base_url, keyword=args.keyword, debug=args.debug)
    print_menu(nodes, keyword=args.keyword)
    return 0


def cmd_inspect(cfg, args) -> int:
    funid = args.funid or cfg.funid
    if not funid:
        print("請用 --funid 指定，或先在 config.yaml 填 query.funid", file=sys.stderr)
        return 2
    client = _make_client(cfg)
    print(f"正在抓取 funid={funid} 的查詢條件頁 …")
    html, fields = inspect_condition_page(client, cfg.base_url, funid)
    if args.debug:
        path = save_debug_html(html, f"condition_{funid}.html")
        print(f"(原始 HTML 已存至 {path})")
    period_opts = print_condition_page(fields)
    if period_opts:
        latest = max(parse_period(v) for v, _ in period_opts if v.isdigit())
        earliest = min(parse_period(v) for v, _ in period_opts if v.isdigit())
        print(f"\n期間範圍：{format_roc(earliest)} ~ {format_roc(latest)}（最新期 = {latest}）")
        # 用設定的樣板組一條範例網址，方便核對
        tmp_cfg = cfg
        url = build_result_url(tmp_cfg, latest, latest) if funid == cfg.funid else "(funid 與 config 不同，略過範例網址)"
        print(f"\n範例結果網址（最新一期）：\n  {url}")
        print("\n請在瀏覽器開啟上面網址核對是否為正確的『資產負債簡表(102年以後)』；")
        print("若參數不符，請對照實際查詢後的網址，修改 config.yaml 的 result_url_template。")
    return 0


def cmd_update(cfg, args) -> int:
    urls = cfg.download_urls
    if not urls and not cfg.funid:
        print(
            "config.yaml 尚未設定 query.download_urls（建議）或 query.funid。\n"
            "請在瀏覽器查到該表後，把結果頁網址貼到 download_urls。",
            file=sys.stderr,
        )
        return 2
    if urls:
        print(f"共 {len(urls)} 條下載網址。")
    client = _make_client(cfg)

    # 1) 結束期（上界）— CLI --end 優先
    if args.end:
        end = parse_period(args.end)
    elif cfg.end_period == "latest":
        if urls:
            # 用真實下載網址時，以系統當月為上界，實際最新期由回傳資料決定。
            end = current_roc_period()
            print(f"以當月 {format_roc(end)} 為查詢上界（實際最新期以網站回傳為準）。")
        else:
            end = detect_latest_period(client, cfg)
    else:
        end = parse_period(cfg.end_period)

    # 2) 起始期 — CLI --start 優先
    existing = storage.load_existing(cfg.data_file, cfg.sheet_name)
    if args.start:
        start = parse_period(args.start)
    elif cfg.start_period == "auto":
        last = storage.latest_period_in(existing, cfg.period_column)
        if last is None:
            # 沒有歷史資料 -> 預設從民國102年1月開始（102年以後表的起點）
            start = 10201
            print("找不到歷史資料，將從 102年01月 開始全量抓取。")
        else:
            start = next_month(last)
            print(f"歷史資料最後一期：{format_roc(last)}，將從 {format_roc(start)} 開始增量抓取。")
    else:
        start = parse_period(cfg.start_period)

    if start > end:
        print(f"已是最新（歷史最後一期之後沒有新資料）。最新期 = {format_roc(end)}，無需更新。")
        return 0

    # 3) 抓取
    result = fetch(client, cfg, start, end, debug=args.debug)
    print(f"\n抓回表格：{result.df.shape[0]} 列 x {result.df.shape[1]} 欄")
    print("欄位：", list(result.df.columns))

    if args.dry_run:
        print("\n[dry-run] 僅預覽，不寫入檔案。前 10 列：")
        print(result.df.head(10).to_string())
        print(
            "\n請對照你的歷史資料，確認：(1)『期別』欄名 (2)『銀行』欄名，"
            "並填到 config.yaml 的 storage.period_column 與 storage.key_columns。"
        )
        return 0

    # 4) 合併寫回
    merged = storage.merge(existing, result.df, cfg.period_column, cfg.key_columns)
    storage.save(merged, cfg.data_file, cfg.sheet_name)
    print(f"\n已更新並寫入 {cfg.data_file}（合併後共 {merged.shape[0]} 列）。")
    missing = [k for k in cfg.key_columns if k not in result.df.columns]
    if missing:
        print(
            f"⚠ 注意：抓回的表格沒有這些去重鍵欄位 {missing}，增量去重可能未生效。"
            "請看上面實際欄位，調整 config.yaml 的 period_column / key_columns。"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fsc_scraper", description="資產負債簡表(102年以後) 自動抓取")
    parser.add_argument("-c", "--config", default=None, help="設定檔路徑（預設 config.yaml）")
    parser.add_argument("-v", "--verbose", action="store_true", help="顯示詳細日誌")
    sub = parser.add_subparsers(dest="command", required=True)

    p_menu = sub.add_parser("discover-menu", help="列出選單節點與 funid")
    p_menu.add_argument("--keyword", default="資產負債簡表", help="要尋找的節點關鍵字")
    p_menu.add_argument("--debug", action="store_true", help="把每頁原始 HTML 存到 debug/")

    p_insp = sub.add_parser("inspect", help="dump 查詢條件頁")
    p_insp.add_argument("--funid", default=None)
    p_insp.add_argument("--debug", action="store_true", help="另存原始 HTML 到 debug/")

    p_upd = sub.add_parser("update", help="抓最新資料並增量合併")
    p_upd.add_argument("--dry-run", action="store_true", help="只抓取與預覽，不寫檔")
    p_upd.add_argument("--debug", action="store_true", help="另存原始 HTML 到 debug/")
    p_upd.add_argument("--start", default=None, help="覆寫起始民國年月（測試用，如 11502）")
    p_upd.add_argument("--end", default=None, help="覆寫結束民國年月（測試用，如 11503）")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = load_config(args.config)

    handlers = {
        "discover-menu": cmd_discover_menu,
        "inspect": cmd_inspect,
        "update": cmd_update,
    }
    return handlers[args.command](cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
