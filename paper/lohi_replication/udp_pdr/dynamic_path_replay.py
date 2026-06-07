import bisect
import csv
import glob
import os
import re
from dataclasses import dataclass


FSTATE_FILENAME_RE = re.compile(r"^fstate_(\d+)\.txt$")


@dataclass(frozen=True)
class ForwardingStateEntry:
    current: int
    destination: int
    next_hop: int
    current_interface_id: int
    next_hop_interface_id: int


@dataclass(frozen=True)
class ReplayResult:
    status: str
    path: tuple
    directional_hops: tuple
    interface_keys: tuple
    isl_interface_keys: tuple
    gsl_interface_keys: tuple
    gsl_ambiguity: bool
    diagnostic: str

    @property
    def success(self):
        return self.status == "success"


def parse_fstate_delta(path):
    entries = {}
    with open(path, newline="") as f_in:
        reader = csv.reader(f_in)
        for line_number, row in enumerate(reader, 1):
            if not row:
                continue
            if len(row) != 5:
                raise ValueError(
                    "%s:%d expected 5 forwarding-state fields, got %d"
                    % (path, line_number, len(row))
                )
            try:
                values = [int(value) for value in row]
            except ValueError as exc:
                raise ValueError(
                    "%s:%d contains a non-integer forwarding-state field"
                    % (path, line_number)
                ) from exc
            entry = ForwardingStateEntry(*values)
            entries[(entry.current, entry.destination)] = entry
    return entries


def list_fstate_snapshots(dynamic_state_dir):
    snapshots = []
    for path in glob.glob(os.path.join(dynamic_state_dir, "fstate_*.txt")):
        match = FSTATE_FILENAME_RE.match(os.path.basename(path))
        if match:
            snapshots.append((int(match.group(1)), path))
    return sorted(snapshots)


def apply_fstate_delta(state, delta):
    state.update(delta)
    return state


def latest_snapshot_time(snapshot_times, time_ns):
    index = bisect.bisect_right(snapshot_times, int(time_ns)) - 1
    return snapshot_times[index] if index >= 0 else None


def load_forwarding_state_at(dynamic_state_dir, time_ns):
    state = {}
    selected_time = None
    for snapshot_time, path in list_fstate_snapshots(dynamic_state_dir):
        if snapshot_time > time_ns:
            break
        apply_fstate_delta(state, parse_fstate_delta(path))
        selected_time = snapshot_time
    return state, selected_time


def _failure(status, path, diagnostic):
    return ReplayResult(
        status=status,
        path=tuple(path),
        directional_hops=tuple(),
        interface_keys=tuple(),
        isl_interface_keys=tuple(),
        gsl_interface_keys=tuple(),
        gsl_ambiguity=False,
        diagnostic=diagnostic,
    )


def replay_path(state, src, dst, num_satellites, num_nodes, hop_limit=1000):
    src = int(src)
    dst = int(dst)
    if src < 0 or dst < 0 or src >= num_nodes or dst >= num_nodes:
        return _failure("invalid_endpoint", [src], "source or destination is outside node range")
    if src == dst:
        return ReplayResult(
            "success", (src,), tuple(), tuple(), tuple(), tuple(), False, ""
        )

    current = src
    path = [src]
    entries = []
    visited = {src}
    while current != dst:
        if len(entries) >= hop_limit:
            return _failure("hop_limit", path, "path exceeded hop limit %d" % hop_limit)
        entry = state.get((current, dst))
        if entry is None:
            return _failure(
                "missing_entry",
                path,
                "missing forwarding entry for current=%d destination=%d" % (current, dst),
            )
        if entry.next_hop == -1:
            return _failure(
                "no_route",
                path,
                "forwarding entry at node %d explicitly has no route" % current,
            )
        if (
            entry.next_hop < 0
            or entry.next_hop >= num_nodes
            or entry.current_interface_id < 0
            or entry.next_hop_interface_id < 0
        ):
            return _failure(
                "invalid_next_hop",
                path,
                "invalid next hop or interface tuple at node %d" % current,
            )
        if entry.next_hop in visited:
            return _failure(
                "loop",
                path + [entry.next_hop],
                "routing loop reaches node %d more than once" % entry.next_hop,
            )
        if current >= num_satellites and entry.next_hop >= num_satellites:
            return _failure(
                "invalid_next_hop",
                path,
                "ground-station to ground-station forwarding hop is invalid",
            )
        entries.append(entry)
        current = entry.next_hop
        path.append(current)
        visited.add(current)

    directional_hops = []
    interface_keys = []
    isl_keys = []
    gsl_keys = []
    for entry in entries:
        directional_hops.append("%d->%d" % (entry.current, entry.next_hop))
        if entry.current < num_satellites and entry.next_hop < num_satellites:
            key = "ISL:%d->%d" % (entry.current, entry.next_hop)
            isl_keys.append(key)
        else:
            # GSL queues are tracked per sending node on a shared channel.
            key = "GSL:%d->-1" % entry.current
            gsl_keys.append(key)
        interface_keys.append(key)

    return ReplayResult(
        status="success",
        path=tuple(path),
        directional_hops=tuple(directional_hops),
        interface_keys=tuple(interface_keys),
        isl_interface_keys=tuple(isl_keys),
        gsl_interface_keys=tuple(gsl_keys),
        gsl_ambiguity=bool(gsl_keys),
        diagnostic=(
            "GSL queue keys identify the sending interface owner but not a unique "
            "shared-channel receiver"
            if gsl_keys
            else ""
        ),
    )


def build_flow_path_timeline(
    dynamic_state_dir,
    flows,
    algorithm,
    num_satellites,
    num_nodes,
    simulation_end_time_ns,
    hop_limit=1000,
):
    snapshots = list_fstate_snapshots(dynamic_state_dir)
    rows = []
    diagnostics = []
    if not snapshots:
        for _, flow in flows.iterrows():
            rows.append(
                {
                    "algorithm": algorithm,
                    "flow_id": int(flow["flow_id"]),
                    "src": int(flow["src"]),
                    "dst": int(flow["dst"]),
                    "interval_start_ns": int(flow["start_time_ns"]),
                    "interval_end_ns": int(flow["end_time_ns"]),
                    "snapshot_time_ns": "",
                    "replay_status": "missing_snapshot",
                    "path_nodes": "",
                    "directional_hops": "",
                    "directional_interface_keys": "",
                    "isl_interface_keys": "",
                    "gsl_interface_keys": "",
                    "gsl_ambiguity": False,
                    "hop_count": 0,
                    "diagnostic": "no forwarding-state snapshots found",
                }
            )
        return rows, diagnostics

    state = {}
    for index, (snapshot_time, path) in enumerate(snapshots):
        try:
            apply_fstate_delta(state, parse_fstate_delta(path))
        except ValueError as exc:
            diagnostics.append(
                {
                    "algorithm": algorithm,
                    "snapshot_time_ns": snapshot_time,
                    "status": "parse_error",
                    "count": 1,
                    "notes": str(exc),
                }
            )
            continue
        next_snapshot_time = (
            snapshots[index + 1][0]
            if index + 1 < len(snapshots)
            else int(simulation_end_time_ns)
        )
        interval_end = min(next_snapshot_time, int(simulation_end_time_ns))
        if interval_end <= snapshot_time:
            continue
        for _, flow in flows.iterrows():
            flow_start = int(flow["start_time_ns"])
            flow_end = int(flow["end_time_ns"])
            overlap_start = max(snapshot_time, flow_start)
            overlap_end = min(interval_end, flow_end)
            if overlap_end <= overlap_start:
                continue
            result = replay_path(
                state,
                flow["src"],
                flow["dst"],
                num_satellites,
                num_nodes,
                hop_limit,
            )
            rows.append(
                {
                    "algorithm": algorithm,
                    "flow_id": int(flow["flow_id"]),
                    "src": int(flow["src"]),
                    "dst": int(flow["dst"]),
                    "interval_start_ns": overlap_start,
                    "interval_end_ns": overlap_end,
                    "snapshot_time_ns": snapshot_time,
                    "replay_status": result.status,
                    "path_nodes": ";".join(str(node) for node in result.path),
                    "directional_hops": ";".join(result.directional_hops),
                    "directional_interface_keys": ";".join(result.interface_keys),
                    "isl_interface_keys": ";".join(result.isl_interface_keys),
                    "gsl_interface_keys": ";".join(result.gsl_interface_keys),
                    "gsl_ambiguity": result.gsl_ambiguity,
                    "hop_count": max(len(result.path) - 1, 0),
                    "diagnostic": result.diagnostic,
                }
            )
    return rows, diagnostics
