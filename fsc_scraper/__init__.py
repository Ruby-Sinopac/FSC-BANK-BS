"""金管會銀行局金融統計資料庫 — 資產負債簡表(102年以後) 自動抓取工具。

模組：
    client    -- HTTP session（瀏覽器標頭、重試、編碼偵測）
    periods   -- 民國年月(ROC year-month)期間處理
    discover  -- 探查網站導覽與查詢條件頁，協助找出 funid / 欄位 / 期間
    scraper   -- 依設定抓取並解析資產負債簡表
    storage   -- 讀寫歷史資料檔、增量合併
    config    -- 讀取 config.yaml
"""

__all__ = ["client", "periods", "discover", "scraper", "storage", "config"]
