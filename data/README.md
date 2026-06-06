# data/

放置歷史與輸出資料檔的資料夾。

把你既有的歷史資料檔放在這裡（預設檔名 `asset_liability_summary.xlsx`，
可於 `config.yaml` 的 `storage.data_file` 調整）。`update` 指令會讀取此檔、
找出最後一期，僅抓取更新的期間並合併寫回。

> 提示：第一次跑完 `update --dry-run` 後，請確認抓回表格的「期間」欄名，
> 並讓它與 `config.yaml` 的 `storage.period_column`、以及你歷史檔的欄名一致，
> 增量去重才會正確運作。
