"""Shared queue-aware link cost helpers.

The default cost model uses seconds throughout:

    propagation delay + transmission delay + queueing delay

The legacy virtual-distance penalty remains available only for controlled
comparisons through ``QUEUE_COST_MODE=legacy_penalty``.
"""

from dataclasses import dataclass
import csv
import math
import os
from typing import Dict, Optional, Tuple


SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
DEFAULT_QUEUE_PACKET_SIZE_BYTES = int(
    os.environ.get("QUEUE_DEFAULT_PACKET_SIZE_BYTES", "1500")
)
DEFAULT_ISL_LINK_CAPACITY_BPS = float(
    os.environ.get("QUEUE_DEFAULT_ISL_CAPACITY_BPS", "1000000000")
)
INCLUDE_TRANSMISSION_DELAY = os.environ.get(
    "QUEUE_INCLUDE_TRANSMISSION_DELAY", "true"
).lower() not in ("0", "false", "no")

_SUPPORTED_QUEUE_COST_MODES = {"delay", "legacy_penalty"}
QUEUE_COST_MODE = os.environ.get("QUEUE_COST_MODE", "delay").strip().lower()
if QUEUE_COST_MODE not in _SUPPORTED_QUEUE_COST_MODES:
    raise ValueError(
        "QUEUE_COST_MODE must be one of %s, got %r"
        % (sorted(_SUPPORTED_QUEUE_COST_MODES), QUEUE_COST_MODE)
    )


@dataclass(frozen=True)
class QueueStatistics:
    queue_packets: Dict[Tuple[int, int], int]
    queue_bytes: Dict[Tuple[int, int], int]
    delay_source: str


def propagation_delay_seconds(distance_m: float) -> float:
    distance = float(distance_m)
    if not math.isfinite(distance) or distance < 0:
        raise ValueError("distance_m must be a finite non-negative value")
    return distance / SPEED_OF_LIGHT_M_PER_S


def calculate_link_delay_cost(
    distance_m: float,
    queue_packets: int = 0,
    queue_bytes: Optional[int] = None,
    link_capacity_bps: Optional[float] = None,
    packet_size_bytes: Optional[int] = None,
    include_transmission_delay: Optional[bool] = None,
) -> float:
    """Return propagation + transmission + queueing delay in seconds."""
    capacity_bps = (
        DEFAULT_ISL_LINK_CAPACITY_BPS
        if link_capacity_bps is None
        else float(link_capacity_bps)
    )
    if not math.isfinite(capacity_bps) or capacity_bps <= 0:
        raise ValueError("link_capacity_bps must be a finite positive value")

    packet_bytes = (
        DEFAULT_QUEUE_PACKET_SIZE_BYTES
        if packet_size_bytes is None
        else int(packet_size_bytes)
    )
    if packet_bytes <= 0:
        raise ValueError("packet_size_bytes must be positive")

    packets = max(0, int(queue_packets or 0))
    if queue_bytes is None:
        queued_bytes = packets * packet_bytes
    else:
        queued_bytes = max(0, int(queue_bytes))

    include_transmission = (
        INCLUDE_TRANSMISSION_DELAY
        if include_transmission_delay is None
        else bool(include_transmission_delay)
    )
    propagation_delay = propagation_delay_seconds(distance_m)
    transmission_delay = packet_bytes * 8.0 / capacity_bps if include_transmission else 0.0
    queueing_delay = queued_bytes * 8.0 / capacity_bps

    # TODO: Add EWMA-smoothed queue delay here to reduce routing flapping.
    return propagation_delay + transmission_delay + queueing_delay


def calculate_legacy_penalty_cost(
    distance_m: float,
    queue_packets: int = 0,
    alpha_dist: float = 0.7,
    alpha_queue: float = 0.3,
    queue_norm_max: int = 100,
    queue_max_penalty_m: float = 2_000_000.0,
) -> float:
    """Return the former virtual-distance penalty cost in meters."""
    normalized_queue = min(
        max(0, int(queue_packets or 0)) / max(1.0, float(queue_norm_max)),
        1.0,
    )
    queue_penalty_m = (
        normalized_queue
        * float(queue_max_penalty_m)
        * (float(alpha_queue) / max(0.01, float(alpha_dist)))
    )
    return float(distance_m) + queue_penalty_m


def calculate_link_queue_cost(
    distance_m: float,
    queue_packets: int = 0,
    queue_bytes: Optional[int] = None,
    link_capacity_bps: Optional[float] = None,
    packet_size_bytes: Optional[int] = None,
    include_transmission_delay: Optional[bool] = None,
    alpha_dist: float = 0.7,
    alpha_queue: float = 0.3,
    queue_norm_max: int = 100,
    queue_max_penalty_m: float = 2_000_000.0,
    cost_mode: Optional[str] = None,
) -> float:
    """Return a queue-aware cost in the active mode's unit."""
    mode = QUEUE_COST_MODE if cost_mode is None else str(cost_mode).strip().lower()
    if mode == "legacy_penalty":
        return calculate_legacy_penalty_cost(
            distance_m,
            queue_packets,
            alpha_dist,
            alpha_queue,
            queue_norm_max,
            queue_max_penalty_m,
        )
    if mode != "delay":
        raise ValueError("Unsupported queue cost mode: %s" % mode)
    return calculate_link_delay_cost(
        distance_m,
        queue_packets=queue_packets,
        queue_bytes=queue_bytes,
        link_capacity_bps=link_capacity_bps,
        packet_size_bytes=packet_size_bytes,
        include_transmission_delay=include_transmission_delay,
    )


def load_queue_statistics_csv(
    queue_stats_file: Optional[str],
    num_satellites: int,
) -> QueueStatistics:
    """Load directional ISL queue maxima, preferring byte occupancy."""
    queue_packets: Dict[Tuple[int, int], int] = {}
    queue_bytes: Dict[Tuple[int, int], int] = {}

    if not queue_stats_file or not os.path.exists(queue_stats_file):
        return QueueStatistics(queue_packets, queue_bytes, "queue_packets_fallback")

    with open(queue_stats_file, "r") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = set(reader.fieldnames or [])
        byte_field = next(
            (
                name
                for name in ("byte_max", "bytes_max", "queue_bytes")
                if name in fieldnames
            ),
            None,
        )
        for row in reader:
            sat_from = int(row["from"])
            sat_to = int(row["to"])
            if sat_from >= num_satellites or sat_to >= num_satellites:
                continue
            key = (sat_from, sat_to)
            queue_packets[key] = max(0, int(float(row.get("packet_max") or 0)))
            if byte_field is not None and row.get(byte_field) not in (None, ""):
                queue_bytes[key] = max(0, int(float(row[byte_field])))

    delay_source = "queue_bytes" if byte_field is not None else "queue_packets_fallback"
    return QueueStatistics(queue_packets, queue_bytes, delay_source)


def get_directional_value(
    values: Optional[Dict[Tuple[int, int], float]],
    u: int,
    v: int,
    default=None,
):
    if not values:
        return default
    if (u, v) in values:
        return values[(u, v)]
    if (v, u) in values:
        return values[(v, u)]
    return default


def describe_queue_cost(
    queue_delay_source: str,
    link_capacity_bps: Optional[float],
) -> str:
    capacity = (
        DEFAULT_ISL_LINK_CAPACITY_BPS
        if link_capacity_bps is None
        else float(link_capacity_bps)
    )
    return (
        "Queue cost mode: %s\n"
        "    >> Queue delay source: %s\n"
        "    >> Default packet size bytes: %d\n"
        "    >> ISL capacity bps: %.0f\n"
        "    >> Include transmission delay: %s"
        % (
            QUEUE_COST_MODE,
            queue_delay_source,
            DEFAULT_QUEUE_PACKET_SIZE_BYTES,
            capacity,
            str(INCLUDE_TRANSMISSION_DELAY).lower(),
        )
    )
