"""
Compare NetworkX RTT outputs across traffic_matrix algorithm runs.
"""

import argparse
import itertools
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


DEFAULT_RUN_DIR = "run_specific_tm_pairing_oneweb_isls_moving_dynamic"
DEFAULT_ALGORITHM_ORDER = [
    "algorithm_queue_aware_over_isls",
    "algorithm_tlr",
    "algorithm_lohi",
    "algorithm_lhtr",
]
RTT_FILE_RE = re.compile(r"^networkx_rtt_(\d+)_to_(\d+)\.txt$")
EPSILON_MS = 1e-9


@dataclass(frozen=True)
class RttSeries:
    name: str
    file_path: Path
    timestamps_ns: np.ndarray
    rtt_ms: np.ndarray

    @property
    def timestamps_s(self):
        return self.timestamps_ns.astype(float) / 1e9

    @property
    def timestamp_set(self):
        return set(self.timestamps_ns.tolist())

    @property
    def timestamp_to_rtt(self):
        return dict(zip(self.timestamps_ns.tolist(), self.rtt_ms.tolist()))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare NetworkX RTT files for two or more traffic_matrix algorithms.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--run-dir",
        default=DEFAULT_RUN_DIR,
        help=(
            "Run folder path, or a run folder name under "
            "paper/lohi_replication/traffic_matrix/data"
        ),
    )
    parser.add_argument("--src", type=int, help="Source node id. Auto-detected if omitted.")
    parser.add_argument("--dst", type=int, help="Destination node id. Auto-detected if omitted.")
    parser.add_argument(
        "--algorithms",
        nargs="+",
        help=(
            "Algorithm folder names under --run-dir. If omitted, available algorithm "
            "folders with networkx_rtt files are auto-detected."
        ),
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory. Defaults to <run-dir>/rtt_comparison.",
    )
    parser.add_argument(
        "--output-prefix",
        default="rtt_comparison",
        help="Legacy prefix for an additional RTT-over-time plot/statistics alias.",
    )
    parser.add_argument(
        "--baseline-algorithm",
        help="Baseline algorithm for the RTT difference plot. Defaults to the first algorithm.",
    )
    parser.add_argument("--width", type=float, default=15.0, help="Figure width in inches.")
    parser.add_argument("--height", type=float, default=6.0, help="Figure height in inches.")
    return parser.parse_args()


def resolve_run_dir(run_dir_arg):
    script_dir = Path(__file__).resolve().parent
    raw_path = Path(run_dir_arg).expanduser()
    candidates = []

    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(Path.cwd() / raw_path)
        candidates.append(script_dir / "data" / raw_path)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    candidate_text = "\n  ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        f"run-dir 不存在，已檢查以下路徑:\n  {candidate_text}"
    )


def resolve_output_dir(output_dir_arg, run_base_dir):
    if output_dir_arg:
        output_dir = Path(output_dir_arg).expanduser()
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
    else:
        output_dir = run_base_dir / "rtt_comparison"

    if output_dir.exists() and not output_dir.is_dir():
        raise OSError(f"output dir 已存在但不是資料夾: {output_dir}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"無法建立 output dir: {output_dir} ({exc})") from exc

    return output_dir.resolve()


def parse_rtt_pair_from_path(file_path):
    match = RTT_FILE_RE.match(file_path.name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def discover_algorithms(run_base_dir):
    discovered = []
    for child in run_base_dir.iterdir():
        if child.is_dir() and any(child.glob("networkx_rtt_*_to_*.txt")):
            discovered.append(child.name)

    ordered = [algo for algo in DEFAULT_ALGORITHM_ORDER if algo in discovered]
    ordered.extend(sorted(algo for algo in discovered if algo not in ordered))

    if len(ordered) < 2:
        raise ValueError(
            "無法自動找到至少兩個含 networkx_rtt 檔案的 algorithm folder: "
            f"{run_base_dir}"
        )
    return ordered


def validate_algorithms(run_base_dir, algorithms):
    if len(algorithms) < 2:
        raise ValueError(f"algorithms 至少需要 2 個，目前是 {len(algorithms)} 個")

    for algo in algorithms:
        algo_dir = run_base_dir / algo
        if not algo_dir.is_dir():
            raise FileNotFoundError(f"algorithm folder 不存在: {algo_dir}")


def available_rtt_pairs(run_base_dir, algo):
    algo_dir = run_base_dir / algo
    pairs = set()
    for file_path in algo_dir.glob("networkx_rtt_*_to_*.txt"):
        pair = parse_rtt_pair_from_path(file_path)
        if pair is not None:
            pairs.add(pair)
    return pairs


def resolve_src_dst(run_base_dir, algorithms, src, dst):
    if (src is None) != (dst is None):
        raise ValueError("--src 與 --dst 必須同時指定，或同時省略讓程式自動偵測")
    if src is not None and dst is not None:
        return src, dst

    pairs_by_algo = {algo: available_rtt_pairs(run_base_dir, algo) for algo in algorithms}
    missing = [algo for algo, pairs in pairs_by_algo.items() if not pairs]
    if missing:
        details = ", ".join(f"{algo}: {run_base_dir / algo}" for algo in missing)
        raise FileNotFoundError(f"找不到 networkx_rtt 檔案: {details}")

    common_pairs = set.intersection(*pairs_by_algo.values())
    if not common_pairs:
        lines = [f"{algo}: {sorted(pairs)}" for algo, pairs in pairs_by_algo.items()]
        raise ValueError(
            "沒有所有 algorithm 共同的 src-dst RTT pair，請用 --src/--dst 指定。\n"
            + "\n".join(lines)
        )
    if len(common_pairs) > 1:
        formatted = ", ".join(f"{s}->{d}" for s, d in sorted(common_pairs))
        raise ValueError(
            "偵測到多個共同 src-dst pair，請用 --src 與 --dst 指定其中一組: "
            f"{formatted}"
        )

    return next(iter(common_pairs))


def find_rtt_file(run_base_dir, algo, src, dst):
    return run_base_dir / algo / f"networkx_rtt_{src}_to_{dst}.txt"


def read_rtt_data(file_path):
    timestamps_ns = []
    rtt_ms = []
    seen_timestamps = set()

    try:
        with file_path.open("r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                parts = line.split(",")
                if len(parts) != 2:
                    raise ValueError(
                        f"RTT file 格式不符合預期: {file_path}:{line_number} "
                        f"應為 timestamp_ns,rtt_ns，實際為 {line!r}"
                    )

                try:
                    timestamp_ns = int(float(parts[0]))
                    rtt_ns = float(parts[1])
                except ValueError as exc:
                    raise ValueError(
                        f"RTT file 數值格式錯誤: {file_path}:{line_number} "
                        f"內容為 {line!r}"
                    ) from exc

                if timestamp_ns in seen_timestamps:
                    raise ValueError(
                        f"RTT file 含重複 timestamp，無法公平對齊: "
                        f"{file_path}:{line_number} timestamp={timestamp_ns}"
                    )

                seen_timestamps.add(timestamp_ns)
                timestamps_ns.append(timestamp_ns)
                rtt_ms.append(rtt_ns / 1e6)
    except OSError as exc:
        raise OSError(f"無法讀取 RTT file: {file_path} ({exc})") from exc

    if not timestamps_ns:
        raise ValueError(f"RTT file 沒有有效資料: {file_path}")

    order = np.argsort(np.array(timestamps_ns, dtype=np.int64))
    timestamps_arr = np.array(timestamps_ns, dtype=np.int64)[order]
    rtt_arr = np.array(rtt_ms, dtype=float)[order]
    return timestamps_arr, rtt_arr


def load_rtt_series(run_base_dir, algorithms, src, dst):
    all_data = {}
    for algo in algorithms:
        file_path = find_rtt_file(run_base_dir, algo, src, dst)
        if not file_path.is_file():
            raise FileNotFoundError(f"RTT file 不存在: {file_path}")

        timestamps_ns, rtt_ms = read_rtt_data(file_path)
        all_data[algo] = RttSeries(
            name=algo,
            file_path=file_path,
            timestamps_ns=timestamps_ns,
            rtt_ms=rtt_ms,
        )
    return all_data


def align_all_series(all_data):
    common_timestamps = set.intersection(
        *(series.timestamp_set for series in all_data.values())
    )
    if not common_timestamps:
        raise ValueError("沒有所有 algorithm 共同的 timestamp 可以比較")

    aligned_timestamps = np.array(sorted(common_timestamps), dtype=np.int64)
    aligned_values = {}
    for algo, series in all_data.items():
        timestamp_to_rtt = series.timestamp_to_rtt
        aligned_values[algo] = np.array(
            [timestamp_to_rtt[int(t)] for t in aligned_timestamps],
            dtype=float,
        )
    return aligned_timestamps, aligned_values


def align_pair(left, right):
    common_timestamps = left.timestamp_set & right.timestamp_set
    if not common_timestamps:
        return np.array([], dtype=np.int64), np.array([], dtype=float), np.array([], dtype=float)

    timestamps = np.array(sorted(common_timestamps), dtype=np.int64)
    left_map = left.timestamp_to_rtt
    right_map = right.timestamp_to_rtt
    left_values = np.array([left_map[int(t)] for t in timestamps], dtype=float)
    right_values = np.array([right_map[int(t)] for t in timestamps], dtype=float)
    return timestamps, left_values, right_values


def compute_alignment_warnings(all_data):
    union_timestamps = set.union(*(series.timestamp_set for series in all_data.values()))
    warnings = []
    for algo, series in all_data.items():
        missing = len(union_timestamps - series.timestamp_set)
        if missing:
            warnings.append(
                f"{algo} 缺少 {missing} / {len(union_timestamps)} 個 union timestamps；"
                "pairwise/statistics 只使用共同 timestamp。"
            )
    return warnings


def rtt_stats(values):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return None
    return {
        "count": int(len(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "std": float(np.std(values)),
        "p50": float(np.percentile(values, 50)),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
    }


def format_stats_block(name, values, indent="  "):
    stats = rtt_stats(values)
    if stats is None:
        return f"{name}\n{indent}(無有效資料)\n"

    zero_count = int(np.sum(np.asarray(values, dtype=float) == 0))
    return (
        f"{name}\n"
        f"{indent}count: {stats['count']}\n"
        f"{indent}mean RTT: {stats['mean']:.4f} ms\n"
        f"{indent}median RTT: {stats['median']:.4f} ms\n"
        f"{indent}min RTT: {stats['min']:.4f} ms\n"
        f"{indent}max RTT: {stats['max']:.4f} ms\n"
        f"{indent}std RTT: {stats['std']:.4f} ms\n"
        f"{indent}p50 RTT: {stats['p50']:.4f} ms\n"
        f"{indent}p90 RTT: {stats['p90']:.4f} ms\n"
        f"{indent}p95 RTT: {stats['p95']:.4f} ms\n"
        f"{indent}p99 RTT: {stats['p99']:.4f} ms\n"
        f"{indent}RTT=0 count: {zero_count}\n"
    )


def build_statistics_text(run_base_dir, src, dst, algorithms, all_data, aligned_timestamps, aligned_values, warnings):
    lines = []
    lines.append("=== RTT Comparison (traffic_matrix) ===")
    lines.append(f"run_dir: {run_base_dir}")
    lines.append(f"src -> dst: {src} -> {dst}")
    lines.append(f"algorithms: {', '.join(algorithms)}")
    lines.append("")

    lines.append("=== Input RTT files ===")
    for algo in algorithms:
        series = all_data[algo]
        lines.append(f"{algo}: {series.file_path} ({len(series.rtt_ms)} samples)")
    lines.append("")

    lines.append("=== Alignment ===")
    union_count = len(set.union(*(series.timestamp_set for series in all_data.values())))
    lines.append(f"union timestamp count: {union_count}")
    lines.append(f"all-algorithm aligned timestamp count: {len(aligned_timestamps)}")
    lines.append(f"aligned time range: {aligned_timestamps[0] / 1e9:.3f}s - {aligned_timestamps[-1] / 1e9:.3f}s")
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"- {warning}")
    lines.append("")

    lines.append("=== All available samples ===")
    for algo in algorithms:
        lines.append(format_stats_block(algo, all_data[algo].rtt_ms).rstrip())
        lines.append("")

    lines.append("=== Aligned samples only (all algorithms share timestamp) ===")
    for algo in algorithms:
        lines.append(format_stats_block(algo, aligned_values[algo]).rstrip())
        lines.append("")

    matrix = np.column_stack([aligned_values[algo] for algo in algorithms])
    per_timestamp_mean = np.mean(matrix, axis=1)
    lines.append("=== Per-timestamp mean RTT summary (aligned samples) ===")
    lines.append(format_stats_block("mean across algorithms at each timestamp", per_timestamp_mean).rstrip())
    lines.append("")

    lines.append("=== Average RTT over all aligned timestamps ===")
    for algo in algorithms:
        lines.append(f"{algo}: {np.mean(aligned_values[algo]):.4f} ms")
    lines.append("")

    best_counts = {algo: 0 for algo in algorithms}
    worst_counts = {algo: 0 for algo in algorithms}
    for row in matrix:
        best_value = np.min(row)
        worst_value = np.max(row)
        for index, algo in enumerate(algorithms):
            if abs(row[index] - best_value) <= EPSILON_MS:
                best_counts[algo] += 1
            if abs(row[index] - worst_value) <= EPSILON_MS:
                worst_counts[algo] += 1

    lines.append("=== Best algorithm per timestamp (lower RTT; ties counted for each algorithm) ===")
    for algo in algorithms:
        lines.append(f"{algo}: {best_counts[algo]} timestamps")
    lines.append("")

    lines.append("=== Worst algorithm per timestamp (higher RTT; ties counted for each algorithm) ===")
    for algo in algorithms:
        lines.append(f"{algo}: {worst_counts[algo]} timestamps")
    lines.append("")

    lines.append("=== Pairwise comparison (aligned samples per pair) ===")
    for left_algo, right_algo in itertools.combinations(algorithms, 2):
        timestamps, left_values, right_values = align_pair(all_data[left_algo], all_data[right_algo])
        lines.append(f"{left_algo} vs {right_algo}")
        if len(timestamps) == 0:
            lines.append("  (沒有共同 timestamp)")
            lines.append("")
            continue

        diff = left_values - right_values
        left_stats = rtt_stats(left_values)
        right_stats = rtt_stats(right_values)
        left_better = int(np.sum(diff < -EPSILON_MS))
        left_worse = int(np.sum(diff > EPSILON_MS))
        equal = int(np.sum(np.abs(diff) <= EPSILON_MS))

        lines.append(f"  aligned sample count: {len(timestamps)}")
        lines.append(f"  mean RTT difference ({left_algo} - {right_algo}): {np.mean(diff):.4f} ms")
        lines.append(f"  median RTT difference ({left_algo} - {right_algo}): {np.median(diff):.4f} ms")
        lines.append(f"  p95 RTT difference ({left_algo} - {right_algo}): {left_stats['p95'] - right_stats['p95']:.4f} ms")
        lines.append(f"  p99 RTT difference ({left_algo} - {right_algo}): {left_stats['p99'] - right_stats['p99']:.4f} ms")
        lines.append(f"  timestamps where {left_algo} is better: {left_better}")
        lines.append(f"  timestamps where {left_algo} is worse: {left_worse}")
        lines.append(f"  timestamps tied: {equal}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def short_algorithm_label(name):
    label = name
    if label.startswith("algorithm_"):
        label = label[len("algorithm_"):]
    label = label.replace("_over_isls", "")
    return label


def make_labels(algorithms):
    labels = {algo: short_algorithm_label(algo) for algo in algorithms}
    seen = {}
    for algo, label in labels.items():
        seen.setdefault(label, []).append(algo)
    for label, duplicate_algos in seen.items():
        if len(duplicate_algos) > 1:
            for algo in duplicate_algos:
                labels[algo] = algo
    return labels


def safe_filename(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "algorithm"


def save_figure(fig, output_dir, basename, output_paths):
    png_path = output_dir / f"{basename}.png"
    pdf_path = output_dir / f"{basename}.pdf"
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, dpi=300, bbox_inches="tight")
    output_paths.extend([png_path, pdf_path])


def configure_common_axes(ax):
    ax.grid(True, linestyle="--", alpha=0.3, color="#999999")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_rtt_over_time(all_data, algorithms, labels, run_name, src, dst, output_dir, width, height, output_prefix):
    fig, ax = plt.subplots(figsize=(width, height))
    colors = plt.get_cmap("tab10")
    ymax = 0.0
    xmax = 0.0

    for index, algo in enumerate(algorithms):
        series = all_data[algo]
        ax.plot(
            series.timestamps_s,
            series.rtt_ms,
            label=labels[algo],
            linewidth=1.4,
            alpha=0.9,
            color=colors(index % 10),
        )
        ymax = max(ymax, float(np.max(series.rtt_ms)))
        xmax = max(xmax, float(np.max(series.timestamps_s)))

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("NetworkX RTT (ms)")
    ax.set_title(f"RTT over time - {run_name} ({src} -> {dst})")
    ax.legend(loc="best")
    configure_common_axes(ax)
    ax.set_xlim(0, xmax)
    if ymax > 0:
        ax.set_ylim(0, ymax * 1.05)
    fig.tight_layout()

    output_paths = []
    save_figure(fig, output_dir, "rtt_over_time", output_paths)
    if output_prefix and output_prefix != "rtt_over_time":
        save_figure(fig, output_dir, output_prefix, output_paths)
    plt.close(fig)
    return output_paths


def plot_rtt_cdf(all_data, algorithms, labels, run_name, src, dst, output_dir, width, height):
    fig, ax = plt.subplots(figsize=(width, height))
    colors = plt.get_cmap("tab10")

    for index, algo in enumerate(algorithms):
        values = np.sort(all_data[algo].rtt_ms)
        cdf = np.arange(1, len(values) + 1, dtype=float) / len(values)
        ax.plot(values, cdf, label=labels[algo], linewidth=1.8, color=colors(index % 10))

    ax.set_xlabel("NetworkX RTT (ms)")
    ax.set_ylabel("CDF")
    ax.set_title(f"RTT CDF - {run_name} ({src} -> {dst})")
    ax.legend(loc="best")
    configure_common_axes(ax)
    ax.set_ylim(0, 1.01)
    fig.tight_layout()

    output_paths = []
    save_figure(fig, output_dir, "rtt_cdf", output_paths)
    plt.close(fig)
    return output_paths


def plot_rtt_boxplot(all_data, algorithms, labels, run_name, src, dst, output_dir, width, height):
    fig, ax = plt.subplots(figsize=(max(width, len(algorithms) * 2.2), height))
    values = [all_data[algo].rtt_ms for algo in algorithms]
    box = ax.boxplot(
        values,
        tick_labels=[labels[algo] for algo in algorithms],
        showmeans=True,
        patch_artist=True,
    )
    colors = plt.get_cmap("tab10")
    for index, patch in enumerate(box["boxes"]):
        patch.set_facecolor(colors(index % 10))
        patch.set_alpha(0.35)

    ax.set_xlabel("Algorithm")
    ax.set_ylabel("NetworkX RTT (ms)")
    ax.set_title(f"RTT distribution - {run_name} ({src} -> {dst})")
    configure_common_axes(ax)
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()

    output_paths = []
    save_figure(fig, output_dir, "rtt_boxplot", output_paths)
    plt.close(fig)
    return output_paths


def plot_rtt_difference_vs_baseline(all_data, algorithms, labels, baseline_algo, run_name, src, dst, output_dir, width, height):
    if baseline_algo not in all_data:
        raise ValueError(
            f"baseline algorithm 不在 algorithms 中: {baseline_algo}; "
            f"可用值: {', '.join(algorithms)}"
        )

    fig, ax = plt.subplots(figsize=(width, height))
    colors = plt.get_cmap("tab10")
    baseline = all_data[baseline_algo]
    plotted = False

    for index, algo in enumerate(algorithms):
        if algo == baseline_algo:
            continue
        timestamps, baseline_values, other_values = align_pair(baseline, all_data[algo])
        if len(timestamps) == 0:
            continue

        diff = other_values - baseline_values
        ax.plot(
            timestamps.astype(float) / 1e9,
            diff,
            label=f"{labels[algo]} - {labels[baseline_algo]}",
            linewidth=1.4,
            alpha=0.9,
            color=colors(index % 10),
        )
        plotted = True

    if not plotted:
        plt.close(fig)
        raise ValueError(f"沒有 algorithm 與 baseline 共享 timestamp: {baseline_algo}")

    ax.axhline(0.0, color="#444444", linewidth=1.0, linestyle="--")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("RTT difference (ms)")
    ax.set_title(f"RTT difference vs {labels[baseline_algo]} - {run_name} ({src} -> {dst})")
    ax.legend(loc="best")
    configure_common_axes(ax)
    fig.tight_layout()

    output_paths = []
    basename = f"rtt_pairwise_diff_vs_{safe_filename(baseline_algo)}"
    save_figure(fig, output_dir, basename, output_paths)
    plt.close(fig)
    return output_paths


def write_statistics(output_dir, output_prefix, text):
    paths = [output_dir / "statistics.txt"]
    legacy_name = f"{output_prefix}_statistics.txt"
    if output_prefix and legacy_name != "statistics.txt":
        paths.append(output_dir / legacy_name)

    for path in paths:
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise OSError(f"無法寫入 statistics file: {path} ({exc})") from exc
    return paths


def main():
    args = parse_args()

    try:
        run_base_dir = resolve_run_dir(args.run_dir)
        algorithms = args.algorithms or discover_algorithms(run_base_dir)
        validate_algorithms(run_base_dir, algorithms)
        src, dst = resolve_src_dst(run_base_dir, algorithms, args.src, args.dst)
        output_dir = resolve_output_dir(args.output_dir, run_base_dir)
        all_data = load_rtt_series(run_base_dir, algorithms, src, dst)
        warnings = compute_alignment_warnings(all_data)
        aligned_timestamps, aligned_values = align_all_series(all_data)

        baseline_algo = args.baseline_algorithm or algorithms[0]
        labels = make_labels(algorithms)
        run_name = run_base_dir.name

        statistics_text = build_statistics_text(
            run_base_dir,
            src,
            dst,
            algorithms,
            all_data,
            aligned_timestamps,
            aligned_values,
            warnings,
        )

        output_paths = []
        output_paths.extend(write_statistics(output_dir, args.output_prefix, statistics_text))
        output_paths.extend(
            plot_rtt_over_time(
                all_data,
                algorithms,
                labels,
                run_name,
                src,
                dst,
                output_dir,
                args.width,
                args.height,
                args.output_prefix,
            )
        )
        output_paths.extend(
            plot_rtt_cdf(
                all_data,
                algorithms,
                labels,
                run_name,
                src,
                dst,
                output_dir,
                args.width,
                args.height,
            )
        )
        output_paths.extend(
            plot_rtt_boxplot(
                all_data,
                algorithms,
                labels,
                run_name,
                src,
                dst,
                output_dir,
                args.width,
                args.height,
            )
        )
        output_paths.extend(
            plot_rtt_difference_vs_baseline(
                all_data,
                algorithms,
                labels,
                baseline_algo,
                run_name,
                src,
                dst,
                output_dir,
                args.width,
                args.height,
            )
        )
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print("=== RTT Comparison 完成 ===")
    print(f"run_dir: {run_base_dir}")
    print(f"src -> dst: {src} -> {dst}")
    print(f"algorithms: {', '.join(algorithms)}")
    print(f"output_dir: {output_dir}")
    print("outputs:")
    for path in output_paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
