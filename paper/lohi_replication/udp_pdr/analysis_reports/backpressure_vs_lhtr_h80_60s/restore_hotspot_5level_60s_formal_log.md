# Restore Log: hotspot_5level_60s_formal

- Backup directory: `analysis_reports/backpressure_vs_lhtr_h80_60s/backup_overwritten_hotspot_5level_60s_formal`
- Backed up accident-version files:
  - `hotspot_5level_60s_formal_status.md`
  - `hotspot_5level_60s_formal_summary.csv`
- Restored shared formal files:
  - `analysis_reports/hotspot_5level_60s_formal/hotspot_5level_60s_formal_status.md`
  - `analysis_reports/hotspot_5level_60s_formal/hotspot_5level_60s_formal_summary.csv`
- Restore method: `git restore` could not create `.git/index.lock` under the sandbox's read-only `.git`, so the files were restored from `HEAD` content with read-only `git show HEAD:<path>` redirected to the workspace files.
- Verification: after restore, `git diff -- paper/lohi_replication/udp_pdr/analysis_reports/hotspot_5level_60s_formal` produced no output.

Root cause: `run_hotspot_5level_60s_formal.py` used a duration-only shared output path and rebuilt the formal manifest/summary/status after execution. With `--scenarios H80` and a CLI algorithm list that included Backpressure, the shared five-level report was rebuilt as if every scenario should also have Backpressure results, producing missing-output rows and incomplete warnings. A second bug made the damage easier to miss: `run_name_for_scenario()` only passed the first algorithm to `get_udp_pdr_run_list()`, so Backpressure identity tags were omitted when the first algorithm was Baseline.
