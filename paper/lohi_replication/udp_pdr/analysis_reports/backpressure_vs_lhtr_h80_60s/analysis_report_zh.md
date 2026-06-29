# 1. 總結

這次 H80 60s 的 Backpressure 結果不適合解讀成「完整 Backpressure 已輸給 LHTR」；它是 restricted-route、destination-proxy、node-total-queue 的 Backpressure variant。成對比較下，LHTR 明顯較好：aggregate PDR 88.68% 對 66.25%，Backpressure 低 -22.44 p.p.；focus PDR 92.93% 對 44.39%，Backpressure 低 -48.54 p.p.。Backpressure lost packets 多 98,317，mean RTT 也從 LHTR 的 234.3 ms 拉高到 1,230 ms。

最核心原因不是 loop：Backpressure path replay 成功率 100.00%、loop_detected_ratio 0.00%、avg path stretch 1。真正問題是壓力決策幾乎沒有生效：fallback_ratio 95.76%，positive_pressure_ratio 只有 4.03%，大多數 fallback 原因是 forward-progress guard 後沒有正壓力候選，因此退回 shortest path，最後仍把流量壓在 ISL hotspot 上。

# 2. 使用資料

- 新 Backpressure+LHTR paired run: `run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_bp_qnodebytes_fbsp_lgfwphop_oneweb_isls_moving_udp_pdr`
- 舊四演算法 H80 60s run: `run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr`
- 情境: H80, simulation 60 s, traffic stop 58 s, src 754, dst 785, load 1.6x, background flows 32, ISL 10 Mbps, GSL 100 Mbps。
- Backpressure variant: requested queue source `node_total_bytes`，effective queue source `node_total_queue_bytes`，fallback `shortest_path`，loop guard `forward_progress_hop`，commodity mode `destination_proxy`。

# 3. Restore 結果

已備份事故版本並還原 shared formal output：

- Backup: `analysis_reports/backpressure_vs_lhtr_h80_60s/backup_overwritten_hotspot_5level_60s_formal/`
- Restore log: `analysis_reports/backpressure_vs_lhtr_h80_60s/restore_hotspot_5level_60s_formal_log.md`
- 驗證結果：`analysis_reports/hotspot_5level_60s_formal/` 還原後沒有 git diff。

# 4. Root cause of accidental overwrite

`run_hotspot_5level_60s_formal.py` 原本使用 duration-only shared output path：`analysis_reports/hotspot_5level_60s_formal/`。H80-only command 加上 Backpressure 演算法後，runner 在結尾仍重建 shared manifest/summary/status，而且 `ALGORITHMS` 取自這次 CLI，因此 formal summary 被改成期待五個情境都有 Backpressure；其他 H40/H60/H90/H100+ 自然變成 missing/incomplete warning。

另外還有一個 run-folder lookup bug：`run_name_for_scenario()` 只把第一個 algorithm 傳給 `get_udp_pdr_run_list()`。當 CLI algorithm list 第一個是 Baseline、但後面包含 Backpressure 時，run name lookup 會漏掉 `bp_q...` identity tag，導致 summary/manifest 更容易指到舊四演算法 run folder，而不是新的 BP-tagged run folder。

已加 guard：default 五情境、四演算法 formal 行為不變；subset 或 custom/BP algorithm 預設寫到 isolated formal output，只有明確加 `--update-shared-formal-summary` 才會更新 shared formal summary。也已修正 run-folder lookup，改用完整 algorithm list 保留 BP identity tag。

# 5. Backpressure vs LHTR H80 60s 比較

| algorithm | aggregate_pdr | focus_pdr | background_pdr | lost_packets | mean_rtt_ms | p95_rtt_ms | dominant_loss_attribution |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LHTR | 88.68% | 92.93% | 88.42% | 49,596 | 234.3 | 310.3 | isl_saturation_associated_loss:49596 |
| Backpressure | 66.25% | 44.39% | 67.61% | 147,913 | 1,230 | 1,488.7 | isl_saturation_associated_loss:147913 |

Backpressure 比 LHTR 差的地方集中在三個層面：第一，focus 754->785 方向 PDR 只有 16.81%，遠低於 LHTR 的 89.49%；第二，ISL saturation samples Backpressure 是 541,046，LHTR 是 42,159；第三，Backpressure mean queue delay 約 1,075.8 ms，而 LHTR 約 64.6 ms。

# 6. Backpressure diagnostics

- fallback_ratio: 95.76%
- positive_pressure_ratio: 4.03%
- candidate_filter_ratio: 52.28%
- forward_progress_success_ratio: 47.72%
- queue_file_exists_ratio: 99.83%
- loop_detected_ratio: 0.00%
- reached_destination_ratio: 100.00%
- avg/p95 path stretch: 1 / 1.05

解讀：loop suppression 確實解掉了繞圈/伸長路徑問題，但 restricted-route BP 的候選太受 forward-progress guard 限制；當 queue pressure 來自 node-total proxy 而非 per-destination/per-interface commodity queue 時，很多候選沒有足夠的正壓力訊號，最後退回 shortest path。這會讓 Backpressure 看起來像「帶著額外震盪與排隊成本的 shortest-path-ish routing」，所以 RTT 與 loss 都變差。

# 7. LHTR diagnostics

- BR selected: 79,369,810
- SBR selected: 92,289，SBR ratio 0.12%
- fallback: 0
- top reasons: `br_green:72.910%;no_alternative_candidate:24.784%;sbr_stretch_too_high:2.188%;sbr_due_to_yellow:0.098%;sbr_due_to_red:0.018%`
- avg yellow/red links: 32.43 / 12.29
- max yellow/red links: 60 / 25

解讀：LHTR 不是靠大量繞路取勝；它大多維持 BR，少量 SBR 在 yellow/red 訊號出現時介入。這比 Backpressure 的 node-total proxy 更穩，因為 LHTR 的 traffic-light 訊號直接把擁塞邊界轉成路由狀態，不需要在每個 next-hop candidate 上找到正壓力梯度。

# 8. 舊 LHTR vs 新 LHTR sanity check

| metric | old | new | match |
| --- | --- | --- | --- |
| aggregate_pdr | 0.8868255192526231 | 0.8868255192526231 | true |
| focus_flow_pdr | 0.9293195748312515 | 0.9293195748312515 | true |
| total_lost_packets | 49596 | 49596 | true |
| min_flow_pdr | 0.8123981689813019 | 0.8123981689813019 | true |
| p5_flow_pdr | 0.8395104352548685 | 0.8395104352548685 | true |
| jain_fairness | 0.9982266010784042 | 0.9982266010784042 | true |
| mean_queue_aware_rtt_ms | 234.30902498052654 | 234.30902498052654 | true |
| p95_queue_aware_rtt_ms | 310.345026489878 | 310.34502648987797 | true |
| mean_propagation_only_rtt_ms | 169.68104838844403 | 169.68104838844403 | true |
| synthetic_lost_packets | 49596 | 49596 | true |
| udp_burst_schedule_sha256 | 4168f5afb2e5ad38a11e88b58db4747a3bd4d095c00e4d3bbb81c206d6b365c7 | 4168f5afb2e5ad38a11e88b58db4747a3bd4d095c00e4d3bbb81c206d6b365c7 | true |
| flow_selection_hash | a9ec9e0a00088d96 | a9ec9e0a00088d96 | true |
| selection_input_hash | dafd5d4e2bbf9755 | dafd5d4e2bbf9755 | true |

Sanity check 結果：13/13 項一致。`udp_burst_schedule.csv` hash、flow_selection_hash、selection_input_hash 皆一致；新 run 裡的 LHTR 可以作為 Backpressure 的 paired baseline。

# 9. 新增輸出檔案

- `analysis_reports/backpressure_vs_lhtr_h80_60s/analysis_report_zh.md`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_summary.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_rtt.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_loss.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_diagnostics_h80_60s.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_diagnostics_h80_60s.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_sanity_check_old_vs_new_h80_60s.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/restore_hotspot_5level_60s_formal_log.md`

Figures:

- `analysis_reports/backpressure_vs_lhtr_h80_60s/figures/backpressure_vs_lhtr_h80_60s_overview.png`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/figures/backpressure_vs_lhtr_h80_60s_pdr_rtt.png`

# 10. 論文 / 教授報告建議

建議不要把這條曲線標成 full Backpressure。更準確的標籤是「restricted-route queue-proxy Backpressure」。在報告中可以把它放在消融/negative result：loop suppression 能避免 path loop，但 queue proxy 與 forward-progress guard 讓大部分決策 fallback，無法有效卸載 hotspot。這個結果反而支持 LHTR 的設計主張：用 link/traffic-light 狀態做穩定的 coarse-grained diversion，比 node-total pressure proxy 更可靠。

# 11. 下一步建議

1. 若要繼續 Backpressure，下一個 variant 應優先測 `interface` 或 per-destination/per-commodity queue source，否則正壓力訊號太粗。
2. 保留 `forward_progress_hop` loop guard，但另測「可接受一小段 stretch」的 guard，避免把所有可用卸載候選都濾掉。
3. 跑 10s/20s smoke 做 diagnostics 先篩選 fallback_ratio；若 fallback_ratio 仍高於 80%，不建議直接跑 60s formal。
4. 論文主線可把 LHTR vs Queue-aware vs LoHi 當主結果，Backpressure restricted-route variant 當設計風險分析。

# 12. Commit 建議

建議拆成一個 commit：

`Protect hotspot formal summaries and add H80 Backpressure comparison`

包含 runner guard、read-only 分析腳本、獨立 report folder 與 restore log。不要把大型 run folder 或事故 backup 外的既有 shared formal diff 放進 commit。
