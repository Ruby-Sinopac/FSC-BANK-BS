# FSC-BANK-BS｜資產負債簡表(102年以後) 自動抓取

自動抓取金管會銀行局「**金融統計資料庫動態查詢系統**」中
[自選統計項查詢](https://survey.banking.gov.tw/statis/webMain.aspx?sys=100&funid=defqry)
左側樹狀選單裡的「**資產負債簡表(102年以後)**」，並把最新一期增量合併到你既有的歷史資料檔。

> ⚠️ **重要：請在「有正常對外網路」的機器上執行。**
> 這套工具是針對 `survey.banking.gov.tw` 設計的。開發環境因網路白名單限制無法連到該站，
> 因此程式是依該系統已知的網址規則寫成的**通用樣板**，第一次使用時需依下方步驟，
> 用內建的「探查工具」確認你那張表的 `funid` 與參數。

---

## 這個系統怎麼運作（給維護者看）

該站是 ASP.NET 的 `statis` 系統，實際資料由 `stmain.jsp` 以**網址參數**產生，例如：

```
https://survey.banking.gov.tw/statis/stmain.jsp?sys=220&ym=10201&ymt=11412&kind=21&type=1&funid=iXXXXX&cycle=41&outmode=0&compmode=00&outkind=1&rdm=亂數
```

關鍵參數：

| 參數 | 意義 |
|------|------|
| `funid` | 哪一張表（資產負債簡表102年以後有自己的 funid） |
| `ym` / `ymt` | 起 / 迄民國年月，格式 `民國年(3碼)+月(2碼)`，如 `10201` = 民國102年1月 |
| `outmode` | 輸出格式：`0` = HTML 網頁（最穩定，程式自動解析表格） |
| `rdm` | 防快取亂數（程式自動產生） |

「最新一期」是從**查詢條件設定頁的期間下拉選單**自動讀出來的——選單裡最大的那個年月就是最新期，所以能自動跟到最近期。

---

## 安裝

需要 Python 3.10+。

```bash
pip install -r requirements.txt
```

---

## 使用三步驟

### 步驟 1：找出「資產負債簡表(102年以後)」的 funid

```bash
python -m fsc_scraper discover-menu
```

會抓網站導覽並列出所有節點，把含「資產負債簡表」的節點特別標出來，例如：

```
funid=i10010     金融機構資產負債簡表－本國銀行(全行)
    https://survey.banking.gov.tw/statis/webMain.aspx?...funid=i10010
```

從清單中挑出**「(102年以後)」**那一張（注意區分本國銀行/外國銀行在臺分行等不同對象，
以及「102年以前 / 以後」兩個版本），把它的 `funid` 填到 `config.yaml` 的 `query.funid`。

> 若清單中找不到（選單可能用 JavaScript 動態載入），請把指令輸出整段貼給我，我幫你定位。

### 步驟 2：確認欄位與期間

```bash
python -m fsc_scraper inspect --funid i10010 --debug
```

會 dump 該表查詢條件頁的所有表單欄位、可選的期間（民國年月），並印出期間範圍與一條
**最新一期的範例網址**。請把那條網址貼到瀏覽器，確認開出來真的是你要的那張表。
若參數對不上，依實際查詢後的網址調整 `config.yaml` 的 `result_url_template`。

### 步驟 3：執行更新

先用 `--dry-run` 看抓回來的表長什麼樣（不寫檔）：

```bash
python -m fsc_scraper update --dry-run
```

確認欄位正確（特別是 `config.yaml` 的 `storage.period_column` 要對到實際的「期間」欄名），
再正式執行：

```bash
python -m fsc_scraper update
```

程式會：
1. 自動偵測網站最新一期；
2. 讀你的歷史檔（`storage.data_file`），找出最後一期；
3. 只抓「最後一期之後 ～ 最新期」的新資料；
4. 依期間去重、排序後合併寫回。

若已是最新，會直接顯示「無需更新」。

---

## 設定檔 `config.yaml`

所有設定都有中文註解，最常需要動的是：

- `query.funid` — 步驟 1 找到的表 id（**必填**）
- `query.result_url_template` — 取資料的網址樣板（步驟 2 核對）
- `storage.data_file` — 你的歷史/輸出檔（`.xlsx` 或 `.csv`）
- `storage.period_column` — 用來判斷最後一期與去重的欄名

---

## 排程自動更新

### 方式 A：本機排程

- **Windows 工作排程器**：每月固定日期執行 `python -m fsc_scraper update`
- **Linux/macOS cron**：例如每月 5 號早上 9 點
  ```cron
  0 9 5 * * cd /path/to/FSC-BANK-BS && python -m fsc_scraper update >> update.log 2>&1
  ```

### 方式 B：GitHub Actions

倉庫內已附 `.github/workflows/update.yml`（每月排程 + 可手動觸發），
會自動執行更新並把變更的資料檔 commit 回倉庫。
**前提是 GitHub Actions runner 連得到 `survey.banking.gov.tw`**（公開站台通常可以）。

---

## 疑難排解

| 狀況 | 處理 |
|------|------|
| `discover-menu` 找不到目標表 | 選單可能是動態載入，請貼輸出給我，或直接用 `inspect --funid` 試已知 funid |
| 抓回的表格欄位怪怪的 / 沒有「期間」欄 | 用 `update --debug` 保存 `debug/result_*.html`，看實際結構後調整 `period_column` 或樣板 |
| 出現亂碼 | 把 `config.yaml` 的 `site.encoding` 從 `auto` 改成 `utf-8` 或 `big5` |
| 403 Forbidden | 確認在有對外網路的機器執行；`http.user_agent` 已預設瀏覽器標頭 |
| 想重抓全部 | 把 `query.start_period` 設成 `10201`（民國102年1月） |

---

## 專案結構

```
config.yaml              設定檔（含中文註解）
requirements.txt         相依套件
fsc_scraper/
  __main__.py            CLI 入口（discover-menu / inspect / update）
  config.py              讀取設定
  client.py              HTTP（瀏覽器標頭、重試、編碼偵測）
  periods.py             民國年月期間運算
  discover.py            探查選單與查詢條件頁
  scraper.py             抓取與表格解析
  storage.py             歷史檔讀寫、增量合併去重
data/                    歷史/輸出資料檔
.github/workflows/       GitHub Actions 排程
```
