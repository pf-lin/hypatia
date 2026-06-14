# Thesis Next Step

## 唯一優先事項

**開始整理論文實驗章節與圖表。**

理由：H80 200s 完整重現 60s 的 PDR 與 RTT 排序；LHTR-LoHi PDR gain 為 28.85 pp，與 60s 的 28.93 pp 幾乎相同。5-level 60s 已提供 severity curve，H80 200s 已提供長時間穩定性證據。

H100+ 200s 可保留為 optional stress-test backup，但不應阻塞論文撰寫。現階段也不建議修改 LHTR/LoHi policy，因為那會改變已完成 formal experiment 的比較基準並延後主線。

建議直接使用：

- `analysis_report_zh.md` 作分析依據。
- `professor_report_zh.md` 作教授報告底稿。
- `thesis_recommended_figures.csv` 安排主文、附錄與 backup figures。
- `figures/` 中五張圖作長時間驗證與 gap 敘事。

## 論文敘事邊界

- Queue-aware 是 ideal upper bound，不是 LHTR 必須超越的 deployable competitor。
- RTT 是 queue-history-based estimate，不是 packet-level measured RTT。
- Loss attribution 是 saturation association，不是 physical drop proof。
- 單次 formal runs 支撐固定 scenario 結論，但不宣稱跨 seed 統計普遍性。
