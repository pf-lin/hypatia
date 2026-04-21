"""
LHTR (Load-aware Hierarchical Traffic Routing) Algorithm
============================================================

基於 LoHi 的 queue-aware 階層式路由算法。

主要改進：
1. 保留 LoHi 的 hierarchical / clustering routing 架構
2. 增強 queue-aware 機制：
   - 從 NS-3 CSV 檔案讀取即時 queue 統計
   - 群內與跨群邊界選擇都考慮 queue 狀態
   - 動態調整路由權重基於 queue occupancy
3. 不引入 traffic-light decision (與 TLR 不同)
4. 相容原有 LoHi 介面，新增參數都有默認值

修改歷史：
- 基於 algorithm_lohi_kun.py
- 參考 algorithm_queue_aware_over_isls.py 的 queue 讀取機制
- 參考 algorithm_tlr.py 的 queue metrics 但不使用 traffic-light logic
"""
from dataclasses import dataclass
from typing import Dict, Set, Tuple, List, Optional, Callable, Any
from collections import Counter, defaultdict
import csv
import datetime as _dt
import heapq
import json
import math
import networkx as nx
import os
import random
import threading
import sys

# ==========================
# Tunables (LoHi p×s)
# ==========================
PLANES_PER_GROUP = int(os.environ.get('LHTR_PLANES_PER_GROUP', 6))
SATS_PER_PLANE_IN_GROUP = int(os.environ.get('LHTR_SATS_PER_PLANE', 10))

# Queue-aware weights
BETA_Q = float(os.environ.get('LHTR_BETA_Q', 1.0))   # queue delay weight
BETA_S = float(os.environ.get('LHTR_BETA_S', 0.0))   # static penalty

# ===== Queue-aware parameters =====
# QUEUE-AWARE: Weight blending for distance vs queue
ALPHA_DISTANCE = float(os.environ.get('LHTR_ALPHA_DISTANCE', 0.7))  # distance weight
ALPHA_QUEUE = float(os.environ.get('LHTR_ALPHA_QUEUE', 0.3))        # queue weight

# QUEUE-AWARE: Queue normalization and penalty
QUEUE_NORMALIZE_MAX_PACKETS = int(os.environ.get('LHTR_QUEUE_NORM_MAX', 100))  # max packets for normalization
QUEUE_MAX_PENALTY_M = float(os.environ.get('LHTR_QUEUE_MAX_PENALTY_M', 2000000.0))  # max penalty distance in meters

# ===== Chaos Monkey =====
ENABLE_CHAOS_MONKEY = os.environ.get('ENABLE_CHAOS_MONKEY', 'false').lower() == 'true'
CHAOS_FAILURE_RATE = float(os.environ.get('CHAOS_FAILURE_RATE', '0.01'))
CHAOS_INTERVAL_SNAPSHOTS = int(os.environ.get('CHAOS_INTERVAL_SNAPSHOTS', '20'))
CHAOS_LOG_FILE = os.environ.get('CHAOS_LOG_FILE', 'chaos_monkey_lhtr.log')

# Management-hop switches
ENFORCE_MGMT_HOP_CROSS_PID = os.environ.get('LHTR_ENFORCE_MGMT_HOP_CROSS_PID', '0') not in ['0','false','False']
ENFORCE_MGMT_HOP_SAME_PID  = os.environ.get('LHTR_ENFORCE_MGMT_HOP_SAME_PID', '0') not in ['0','false','False']

# Group-level cost
TG_MODE = os.environ.get('LHTR_TG_MODE', 'constant')
TG_CONST_NG = int(os.environ.get('LHTR_TG_CONST_NG', 10))
TG_CONST_LAVG_BYTES = int(os.environ.get('LHTR_TG_CONST_LAVG', 1500))
LINK_BW_BPS_DEFAULT = float(os.environ.get('LHTR_LINK_BW_BPS', 1_000_000_000))
TG_SCALE = float(os.environ.get('LHTR_TG_SCALE', 1.0))

# ==========================
# QUEUE-AWARE: Load queue statistics from CSV
# ==========================
def load_queue_statistics_from_csv(queue_stats_file: str, num_satellites: int, enable_verbose_logs: bool = False) -> Dict[Tuple[int,int], int]:
    """
    QUEUE-AWARE: 從 NS-3 輸出的 queue 統計檔案讀取數據
    
    Args:
        queue_stats_file: CSV 檔案路徑
        num_satellites: 衛星總數
        enable_verbose_logs: 是否輸出詳細日誌
    
    Returns:
        dict: {(sat_from, sat_to): queue_length_packets}
    
    CSV 格式假設：
        from,to,packet_max,bytes_max,...
    """
    queue_delays = {}
    
    if not queue_stats_file or not os.path.exists(queue_stats_file):
        if enable_verbose_logs:
            print(f"  > [QUEUE-AWARE] Queue statistics file not found or not provided: {queue_stats_file}")
        return queue_delays
    
    try:
        with open(queue_stats_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sat_from = int(row['from'])
                sat_to = int(row['to'])
                
                # 只處理衛星之間的 ISL (排除 GS)
                if sat_from < num_satellites and sat_to < num_satellites:
                    # 使用 packet_max 作為 queue 指標
                    queue_len = int(row.get('packet_max', 0))
                    queue_delays[(sat_from, sat_to)] = queue_len
        
        # 統計
        if enable_verbose_logs:
            unique_links = set()
            directional_flows_with_traffic = 0
            for (a, b), packets in queue_delays.items():
                link = tuple(sorted([a, b]))
                unique_links.add(link)
                if packets > 0:
                    directional_flows_with_traffic += 1
            
            print("  > [QUEUE-AWARE] Queue statistics loaded:")
            print(f"    >> Total directional flows: {len(queue_delays)}")
            print(f"    >> Directional flows with traffic: {directional_flows_with_traffic}")
            print(f"    >> Unique physical ISL links: {len(unique_links)}")
    
    except Exception as e:
        if enable_verbose_logs:
            print(f"  > [QUEUE-AWARE] Error loading queue statistics: {e}")
    
    return queue_delays


def calculate_link_queue_cost(distance_m: float, queue_packets: int, 
                               alpha_dist: float = ALPHA_DISTANCE, 
                               alpha_queue: float = ALPHA_QUEUE,
                               queue_norm_max: int = QUEUE_NORMALIZE_MAX_PACKETS,
                               queue_max_penalty_m: float = QUEUE_MAX_PENALTY_M) -> float:
    """
    QUEUE-AWARE: 計算結合距離和 queue 的鏈路成本
    
    Args:
        distance_m: 物理距離 (公尺)
        queue_packets: 當前 queue 長度 (封包數)
        alpha_dist: 距離權重係數 (預設 0.7)
        alpha_queue: queue 權重係數 (預設 0.3)
        queue_norm_max: queue 正規化最大值 (預設 100 packets)
        queue_max_penalty_m: queue 滿載時的最大懲罰距離 (預設 2000 km)
    
    Returns:
        float: 加權後的虛擬距離 (公尺)
    
    計算公式：
        normalized_queue = min(queue_packets / queue_norm_max, 1.0)
        queue_penalty = normalized_queue * queue_max_penalty_m * (alpha_queue / alpha_dist)
        final_cost = distance_m + queue_penalty
    """
    # 正規化 queue (0.0 ~ 1.0)
    normalized_queue = min(queue_packets / max(1.0, queue_norm_max), 1.0)
    
    # 計算 queue 懲罰 (換算成等效距離)
    # 使用 alpha 比例調整懲罰強度
    queue_penalty_m = normalized_queue * queue_max_penalty_m * (alpha_queue / max(0.01, alpha_dist))
    
    # 最終成本 = 基礎距離 + queue 懲罰
    final_cost = distance_m + queue_penalty_m
    
    return final_cost


# ==========================
# Chaos Monkey
# ==========================
def chaos_monkey_inject_failures(G_sat_isls, snapshot_idx, failure_rate, log_file='chaos_monkey_lhtr.log'):
    """Chaos Monkey: 在當前snapshot隨機移除指定比例的ISL"""
    if not G_sat_isls or G_sat_isls.number_of_edges() == 0:
        return []
    
    all_isls = [(u, v) for u, v in G_sat_isls.edges()]
    if not all_isls:
        return []
    
    num_to_remove = max(1, int(len(all_isls) * failure_rate))
    edges_to_remove = random.sample(all_isls, num_to_remove)
    
    removed_count = 0
    for u, v in edges_to_remove:
        if G_sat_isls.has_edge(u, v):
            G_sat_isls.remove_edge(u, v)
            removed_count += 1
    
    timestamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"
    log_msg = (f"{timestamp} [CHAOS_MONKEY] Snapshot={snapshot_idx} "
               f"Total_ISLs={len(all_isls)} Removed={removed_count} Rate={failure_rate:.2%}\n")
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg)
            for u, v in edges_to_remove:
                f.write(f"  - ISL removed: {u} <-> {v}\n")
    except Exception as e:
        print(f"Warning: Could not write to Chaos Monkey log: {e}", file=sys.stderr)
    
    return edges_to_remove


# ==========================
# Control signaling stats
# ==========================
@dataclass
class EventRow:
    snapshot: int
    sim_time_ms: int
    event: str
    count: int = 1
    bytes: int = 0
    detail: Optional[Dict[str, Any]] = None

class ControlSignalingStats:
    """收集和輸出控制面信令統計"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.timeline: List[EventRow] = []
        self.total_bytes = 0
        self.total_events = 0
        self.pid_rebuilds = 0
        self.routing_updates = 0
        self.topology_changes = 0

    def _append(self, row: EventRow):
        self.timeline.append(row)
        self.total_events += row.count
        self.total_bytes += row.bytes

    def record_pid_rebuild(self, snapshot, ms, changed_pids:int):
        self.pid_rebuilds += 1
        self._append(EventRow(snapshot, ms, 'pid_rebuild', 1, 0,
                              {'changed_pids': changed_pids}))

    def record_topology_change(self, snapshot, ms, delta_group_edges:int, delta_isl:int=0):
        self.topology_changes += 1
        self._append(EventRow(snapshot, ms, 'topology_change', 1, 0,
                              {'delta_group_edges': delta_group_edges, 'delta_isl': delta_isl}))

    def record_routing_update(self, snapshot, ms, changed:int, total:int):
        self.routing_updates += 1
        self._append(EventRow(snapshot, ms, 'routing_update', 1, 0,
                              {'changed_entries': changed, 'total_entries': total}))

    def to_json(self):
        by_type = {}
        for event in self.timeline:
            event_type = event.event
            if event_type not in by_type:
                by_type[event_type] = {"count": 0, "bytes": 0}
            by_type[event_type]["count"] += event.count
            by_type[event_type]["bytes"] += event.bytes
        
        return {
            'summary': {
                'total_events': self.total_events,
                'total_bytes': self.total_bytes,
                'by_type': by_type
            },
            'timeline': [
                {
                    'snapshot': row.snapshot,
                    'time_ms': row.sim_time_ms,
                    'event': row.event,
                    'count': row.count,
                    'bytes': row.bytes,
                    'detail': row.detail
                }
                for row in self.timeline
            ]
        }

_thread_local = threading.local()

def _get_process_local_stats():
    if not hasattr(_thread_local, 'stats'):
        _thread_local.stats = ControlSignalingStats()
    return _thread_local.stats

def get_lhtr_signaling_stats():
    return _get_process_local_stats().to_json()


def _dump_pid_snapshot(
    snapshot_idx: int,
    step_ms: int,
    router: "VirtualPIDRouterPlaneBlock",
    gplanner: "GroupPlanner",
    sat_to_pid: Dict[int, int],
    reason_counters: Optional[Dict[str, int]] = None,
    missing_reason_counts: Optional[Dict[str, int]] = None,
) -> None:
    """Debug dump for PID/grouping and fstate missing reasons per timestamp."""
    print(f"=== Timestamp: {snapshot_idx * step_ms} ms (snapshot={snapshot_idx}) ===")
    print("=== PID Summary ===")
    print(f"pid_count={len(router.pid_members)}")
    print("pid_member_count=", {pid: len(mem) for pid, mem in sorted(router.pid_members.items())})
    print("pid_key=", {pid: router.pid_key_map.get(pid) for pid in sorted(router.pid_members.keys())})
    print("pid_mgmt_sat=", {pid: router.pid_mgmt_sat.get(pid) for pid in sorted(router.pid_members.keys())})

    print("=== Connected Components ===")
    pid_comp_counts = {}
    pid_comp_node_counts = {}
    sat_to_comp = {}
    for pid in sorted(router.pid_members.keys()):
        comp_map = router.pid_sat_comp.get(pid, {})
        inv = defaultdict(list)
        for sat, cid in comp_map.items():
            inv[cid].append(sat)
            sat_to_comp[sat] = (pid, cid)
        for cid in inv:
            inv[cid].sort()
        pid_comp_counts[pid] = len(inv)
        pid_comp_node_counts[pid] = {cid: len(nodes) for cid, nodes in sorted(inv.items())}
    print("pid_component_count=", pid_comp_counts)
    print("pid_component_node_count=", pid_comp_node_counts)

    print("=== Sat Mappings ===")
    print("sat_to_pid=", dict(sorted(sat_to_pid.items())))
    print("sat_to_component=", dict(sorted(sat_to_comp.items())))

    print("=== Planner Edge Meta (key fields) ===")
    edge_meta_key = {}
    for (a, b), meta in sorted(gplanner.edge_meta.items()):
        edge_meta_key[(a, b)] = {
            "pid_id": meta.get("pid_id"),
            "weight": meta.get("weight"),
            "isl_pairs_count": len(meta.get("isl_pairs", [])),
        }
    print("edge_meta=", edge_meta_key)

    if reason_counters is not None:
        print("=== Reason Counters ===")
        print(dict(sorted(reason_counters.items())))
    if missing_reason_counts is not None:
        print("=== Missing Fstate Analysis ===")
        print(dict(sorted(missing_reason_counts.items())))


# ==========================
# PID router (p×s)
# ==========================
class VirtualPIDRouterPlaneBlock:
    """
    基於 plane-block 的 PID 分群器 + 每個 PID 的子圖/連通分量映射
    
    - 使用 (plane_id, pos_in_plane) 依固定 p×s 分群
    - 維護群內圖去抖動機制
    """
    def __init__(self, M_down: int = 2, planes_per_group: int = None, sats_per_plane_in_group: int = None):
        self.pid_members: Dict[int, Set[int]] = {}
        self.pid_key_map: Dict[int, Tuple[int,int]] = {}
        self.pid_of_sat: Dict[int,int] = {}
        self.pid_subgraphs: Dict[int, nx.Graph] = {}
        self.pid_sat_comp: Dict[int, Dict[int,int]] = {}
        self.pid_mgmt_sat: Dict[int, int] = {}
        self._prev_pid_of_sat: Dict[int,int] = {}
        self._snapshot_ms = 100
        self._snapshot_idx = 0
        
        self.planes_per_group = planes_per_group if planes_per_group is not None else PLANES_PER_GROUP
        self.sats_per_plane_in_group = sats_per_plane_in_group if sats_per_plane_in_group is not None else SATS_PER_PLANE_IN_GROUP
        
        # 群內圖去抖動
        self.M_down = M_down
        self.intra_edge_down_counter: Dict[int, Dict[Tuple[int,int], int]] = {}
        self.intra_edge_holdover: Dict[int, Dict[Tuple[int,int], dict]] = {}

    def set_snapshot(self, idx:int, step_ms:int):
        self._snapshot_idx = idx
        self._snapshot_ms = step_ms

    @staticmethod
    def _infer_plane_and_pos(node_attrs: dict) -> Tuple[Optional[int], Optional[int]]:
        plane_keys = ['plane','orbital_plane','plane_id','walker_plane','orbit_plane']
        pos_keys   = ['slot','pos_in_plane','index_in_plane','walker_index','sat_index_in_plane']
        plane = None
        pos = None
        for k in plane_keys:
            if k in node_attrs:
                try:
                    plane = int(node_attrs[k])
                    break
                except Exception:
                    pass
        for k in pos_keys:
            if k in node_attrs:
                try:
                    pos = int(node_attrs[k])
                    break
                except Exception:
                    pass
        return plane, pos

    def _build_pid_from_plane_blocks(self, G_sat: nx.Graph) -> None:
        """依 p×s 分群"""
        pid_counter = 0
        self.pid_members.clear(); self.pid_key_map.clear(); self.pid_of_sat.clear(); self.pid_mgmt_sat.clear()
        
        gkey_to_pid: Dict[Tuple[int,int], int] = {}
        
        for sid, attrs in G_sat.nodes(data=True):
            plane, pos = self._infer_plane_and_pos(attrs)
            if plane is None or pos is None:
                plane_block_id = -1
                seg_id_in_plane = (sid // max(1, self.sats_per_plane_in_group)) % self.sats_per_plane_in_group
            else:
                plane_block_id = plane // self.planes_per_group
                seg_id_in_plane = pos // self.sats_per_plane_in_group
            gkey = (plane_block_id, seg_id_in_plane)
            
            if gkey not in gkey_to_pid:
                pid_int = pid_counter
                pid_counter += 1
                gkey_to_pid[gkey] = pid_int
                self.pid_key_map[pid_int] = gkey
                self.pid_members[pid_int] = set()
            else:
                pid_int = gkey_to_pid[gkey]
            
            self.pid_members[pid_int].add(sid)
            self.pid_of_sat[sid] = pid_int
        
        # 選管理衛星
        for pid, mem in list(self.pid_members.items()):
            if not mem:
                continue
            Gp = G_sat.subgraph(mem)
            if len(Gp) == 0:
                continue
            try:
                degs = Gp.degree()
                max_deg = max(d for _, d in degs)
                cands = [n for n, d in Gp.degree() if d == max_deg]
                self.pid_mgmt_sat[pid] = min(cands)
            except Exception:
                self.pid_mgmt_sat[pid] = min(mem)

    def refresh_pid_members_and_subgraphs(self,
                                          sat_ids: List[int],
                                          G_sat: nx.Graph) -> Dict[int,int]:
        """p×s分群；建立群內子圖與連通分量；回傳 sat->pid"""
        self._build_pid_from_plane_blocks(G_sat)
        self.pid_subgraphs.clear()
        self.pid_sat_comp.clear()
        
        for pid, mem in list(self.pid_members.items()):
            if not mem:
                self.pid_subgraphs[pid] = nx.Graph()
                self.pid_sat_comp[pid] = {}
                continue
            
            Gp_observed = G_sat.subgraph(mem).copy()
            
            if pid not in self.intra_edge_down_counter:
                self.intra_edge_down_counter[pid] = {}
            if pid not in self.intra_edge_holdover:
                self.intra_edge_holdover[pid] = {}
            
            observed_edges = set()
            for u, v in Gp_observed.edges():
                edge_key = (min(u, v), max(u, v))
                observed_edges.add(edge_key)
                self.intra_edge_down_counter[pid][edge_key] = 0
                self.intra_edge_holdover[pid][edge_key] = Gp_observed.get_edge_data(u, v).copy()
            
            holdover_edges = set()
            for edge_key in list(self.intra_edge_down_counter[pid].keys()):
                if edge_key not in observed_edges:
                    self.intra_edge_down_counter[pid][edge_key] += 1
                    
                    if self.intra_edge_down_counter[pid][edge_key] < self.M_down:
                        holdover_edges.add(edge_key)
                    else:
                        del self.intra_edge_down_counter[pid][edge_key]
                        self.intra_edge_holdover[pid].pop(edge_key, None)
            
            Gp = Gp_observed.copy()
            for edge_key in holdover_edges:
                u, v = edge_key
                if not Gp.has_edge(u, v):
                    edge_data = self.intra_edge_holdover[pid].get(edge_key, {})
                    Gp.add_edge(u, v, **edge_data)
            
            self.pid_subgraphs[pid] = Gp
            
            comp_map: Dict[int,int] = {}
            for cid, comp in enumerate(nx.connected_components(Gp)):
                for s in comp:
                    comp_map[s] = cid
            self.pid_sat_comp[pid] = comp_map
        
        # 控制信令統計
        changed = 0
        if self._prev_pid_of_sat:
            changed_pids = set()
            for sid, p_now in self.pid_of_sat.items():
                p_prev = self._prev_pid_of_sat.get(sid)
                if p_prev is not None and p_prev != p_now:
                    changed_pids.add(p_prev)
                    changed_pids.add(p_now)
            changed = len(changed_pids)
        else:
            changed = sum(1 for _, mem in self.pid_members.items() if mem)
        _get_process_local_stats().record_pid_rebuild(self._snapshot_idx, self._snapshot_ms*self._snapshot_idx, changed)
        self._prev_pid_of_sat = dict(self.pid_of_sat)
        return dict(self.pid_of_sat)


# ==========================
# QUEUE-AWARE: 群內佇列權重 (Enhanced)
# ==========================
def apply_queue_aware_weights_intra_only(G_sat: nx.Graph,
                                         sat_pid: Dict[int,int],
                                         queue_bytes: Optional[Dict[Tuple[int,int], int]],
                                         link_rate_bps: Optional[Dict[Tuple[int,int], float]],
                                         queue_packets: Optional[Dict[Tuple[int,int], int]] = None,
                                         beta_q: float = BETA_Q,
                                         beta_s: float = BETA_S,
                                         use_enhanced_queue_cost: bool = True) -> None:
    """
    QUEUE-AWARE (Enhanced): 僅對群內邊加入排隊延遲處罰，群際邊保留原始 geo_len_m
    
    兩種模式：
    1. 原始模式 (use_enhanced_queue_cost=False):
       weight = geo_len_m + beta_q * (queue_bytes*8 / rate_bps) * C_UNIT + beta_s
    
    2. 增強模式 (use_enhanced_queue_cost=True, 預設):
       使用 calculate_link_queue_cost() 結合距離和 queue packets
       支援更靈活的 alpha/beta 加權
    
    Args:
        G_sat: 衛星圖
        sat_pid: 衛星到 PID 的映射
        queue_bytes: (u,v) -> queue bytes (用於原始模式)
        link_rate_bps: (u,v) -> link rate (用於原始模式)
        queue_packets: (u,v) -> queue packets (用於增強模式)
        beta_q: queue 權重 (原始模式)
        beta_s: 靜態懲罰 (原始模式)
        use_enhanced_queue_cost: 是否使用增強的 queue cost 計算
    """
    C_UNIT = 3e5  # 光速常數 (km/s -> m/s conversion factor)
    
    for u, v, d in G_sat.edges(data=True):
        base = float(d.get('geo_len_m', d.get('weight', 1.0)))
        pa, pb = sat_pid.get(u), sat_pid.get(v)
        
        # 只處理群內邊
        if pa is None or pb is None or pa != pb:
            d['weight'] = base
            continue
        
        # 如果沒有 queue 資料，使用基礎權重
        if use_enhanced_queue_cost and queue_packets:
            # QUEUE-AWARE: 增強模式
            q_packets = None
            if (u, v) in queue_packets:
                q_packets = queue_packets[(u, v)]
            elif (v, u) in queue_packets:
                q_packets = queue_packets[(v, u)]
            
            if q_packets is not None:
                # 使用增強的 queue cost 計算
                d['weight'] = calculate_link_queue_cost(
                    base, q_packets,
                    alpha_dist=ALPHA_DISTANCE,
                    alpha_queue=ALPHA_QUEUE,
                    queue_norm_max=QUEUE_NORMALIZE_MAX_PACKETS,
                    queue_max_penalty_m=QUEUE_MAX_PENALTY_M
                )
            else:
                d['weight'] = base
        else:
            # 原始模式 (向後相容)
            if not queue_bytes or not link_rate_bps:
                d['weight'] = base
                continue
            
            q = None; r = None
            if (u,v) in queue_bytes and (u,v) in link_rate_bps:
                q = queue_bytes[(u,v)]; r = link_rate_bps[(u,v)]
            elif (v,u) in queue_bytes and (v,u) in link_rate_bps:
                q = queue_bytes[(v,u)]; r = link_rate_bps[(v,u)]
            
            if q is not None and r and r > 0:
                q_delay_s = (q * 8.0) / r
                d['weight'] = base + beta_q * q_delay_s * C_UNIT + beta_s
            else:
                d['weight'] = base


# ==========================
# 群圖與群際路徑規劃
# ==========================
class GroupPlanner:
    """維護群圖（以 PID 為節點），並在其上做最短路"""
    def __init__(self, K_up: int = 3, K_down: int = 3):
        self.group_graph = nx.Graph()
        self.prev_edges: Set[Tuple[int,int]] = set()
        self.edge_meta: Dict[Tuple[int,int], Dict[str, any]] = {}
        self._snapshot_idx = 0
        self._snapshot_ms = 100
        self._pid_counter = 0
        
        self.K_up = K_up
        self.K_down = K_down
        self.edge_up_counter: Dict[Tuple[int,int], int] = {}
        self.edge_down_counter: Dict[Tuple[int,int], int] = {}
        self.stable_edges: Set[Tuple[int,int]] = set()

    def set_snapshot(self, idx:int, step_ms:int):
        self._snapshot_idx = idx
        self._snapshot_ms = step_ms

    @staticmethod
    def _compute_Tg(links:int) -> float:
        if TG_MODE.lower() == 'off':
            return 0.0
        Ng = max(1, TG_CONST_NG)
        Lavg_b = max(1, TG_CONST_LAVG_BYTES) * 8.0
        BW = max(1.0, LINK_BW_BPS_DEFAULT)
        Tg = (Ng * Lavg_b) / (max(1, links) * BW)
        return float(Tg)

    def build_group_graph(self, G_sat: nx.Graph, pid_of_sat: Dict[int,int], cost_mode:str='hop'):
        """建構群圖，加入去抖動機制"""
        effective_K_up = 1 if self._snapshot_idx < 5 else self.K_up
        effective_K_down = 1 if self._snapshot_idx < 5 else self.K_down
        
        edge_count: Dict[Tuple[int,int], int] = {}
        isl_pairs: Dict[Tuple[int,int], List[Tuple[int,int]]] = {}
        for u, v, d in G_sat.edges(data=True):
            pa, pb = pid_of_sat.get(u), pid_of_sat.get(v)
            if pa is None or pb is None or pa == pb:
                continue
            a, b = (pa, pb) if pa < pb else (pb, pa)
            edge_count[(a,b)] = edge_count.get((a,b),0) + 1
            isl_pairs.setdefault((a,b), []).append((u,v))
        
        observed_edges = set(edge_count.keys())
        
        for edge in observed_edges:
            self.edge_up_counter[edge] = self.edge_up_counter.get(edge, 0) + 1
            self.edge_down_counter[edge] = 0
            
            if self.edge_up_counter[edge] >= effective_K_up:
                self.stable_edges.add(edge)
        
        for edge in list(self.stable_edges):
            if edge not in observed_edges:
                self.edge_down_counter[edge] = self.edge_down_counter.get(edge, 0) + 1
                self.edge_up_counter[edge] = 0
                
                if self.edge_down_counter[edge] >= effective_K_down:
                    self.stable_edges.discard(edge)
                    self.edge_up_counter.pop(edge, None)
                    self.edge_down_counter.pop(edge, None)
        
        GG = nx.Graph()
        self.edge_meta.clear()
        for (a, b) in self.stable_edges:
            cnt = edge_count.get((a, b), 0)
            if cnt <= 0:
                last = self.edge_meta.get((a, b))
                if last:
                    cnt_last = max(1, last.get('links', 1))
                    Tg = self._compute_Tg(cnt_last)
                    base = 1.0 if cost_mode != 'invlinks' else 1.0 / cnt_last
                    w = (base + TG_SCALE * Tg) * 1.2
                    GG.add_edge(a, b, weight=w, links=cnt_last, Tg=Tg)
                    self.edge_meta[(a, b)] = dict(last)
                continue
            
            base = 1.0 if cost_mode != 'invlinks' else 1.0/max(1,cnt)
            Tg = self._compute_Tg(cnt)
            w = base + TG_SCALE * Tg
            GG.add_edge(a, b, weight=w, links=cnt, Tg=Tg)
            
            pid_id = self._pid_counter
            self._pid_counter += 1
            self.edge_meta[(a, b)] = {
                'pid_id': pid_id, 
                'links': cnt, 
                'isl_pairs': isl_pairs.get((a, b), [])
            }
        
        curr = {(a,b) for (a,b) in GG.edges()}
        delta = len(curr - self.prev_edges) - len(self.prev_edges - curr)
        
        current_isl_count = G_sat.number_of_edges()
        prev_isl_count = getattr(self, '_prev_isl_count', current_isl_count)
        delta_isl = current_isl_count - prev_isl_count
        
        _get_process_local_stats().record_topology_change(self._snapshot_idx, self._snapshot_ms*self._snapshot_idx, delta, delta_isl=delta_isl)
        
        self.prev_edges = curr
        self._prev_isl_count = current_isl_count
        self.group_graph = GG

    def shortest_group_path(self, src_pid:int, dst_pid:int) -> List[int]:
        if src_pid == dst_pid:
            return [src_pid]
        if not self.group_graph.has_node(src_pid) or not self.group_graph.has_node(dst_pid):
            return []
        try:
            return nx.shortest_path(self.group_graph, src_pid, dst_pid, weight='weight')
        except nx.NetworkXNoPath:
            return []

    def get_edge_meta(self, a:int, b:int) -> Optional[Dict[str,any]]:
        x, y = (a,b) if a < b else (b,a)
        return self.edge_meta.get((x,y))
    
    def distances_to(self, dst_pid: int):
        """以目的群為根計算群圖最短路樹"""
        GG = self.group_graph
        if not GG.has_node(dst_pid):
            return {}, {}
        dist = {n: float('inf') for n in GG.nodes()}
        prev = {n: None for n in GG.nodes()}
        dist[dst_pid] = 0.0
        pq = [(0.0, dst_pid)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for v, edata in GG[u].items():
                w = float(edata.get('weight', 1.0))
                nd = d + w
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        return dist, prev


# ==========================
# QUEUE-AWARE: 邊界挑選 (Enhanced)
# ==========================
class BorderSelector:
    """
    QUEUE-AWARE: 從 src_PID 指向 next_PID 的所有實體跨邊中，挑一組 (u_in_src, v_in_next)
    
    策略改進：
    1. 選擇最短 geo_len_m 的邊界對（原始 LoHi）
    2. 分量感知（確保連通性）
    3. QUEUE-AWARE: 考慮邊界 ISL 的 queue 狀態（新增）
    """
    @staticmethod
    def pick_border_pair(G_sat: nx.Graph,
                         gplanner: 'GroupPlanner',
                         src_pid:int,
                         next_pid:int,
                         sat_pid: Dict[int, int],
                         src_sat: Optional[int] = None,
                         router: Optional['VirtualPIDRouterPlaneBlock'] = None,
                         queue_packets: Optional[Dict[Tuple[int,int], int]] = None) -> Optional[Tuple[int,int]]:
        """
        QUEUE-AWARE: 選擇邊界對，優先考慮：
        1. 與來源衛星同分量（src_comp_id）
        2. 與目標 PID 管理衛星同分量
        3. QUEUE-AWARE: queue 狀態（優先選擇低 queue 的邊界）
        4. 最短地理距離
        
        Args:
            queue_packets: (u,v) -> queue packets (新增參數，預設 None)
        """
        meta = gplanner.get_edge_meta(src_pid, next_pid)
        if not meta:
            return None
        
        src_comp_id = None
        if src_sat is not None and router is not None:
            pid_comp_map = router.pid_sat_comp.get(src_pid, {})
            src_comp_id = pid_comp_map.get(src_sat)
        
        next_mgmt_sat = router.pid_mgmt_sat.get(next_pid) if router else None
        next_mgmt_comp_id = None
        if next_mgmt_sat is not None and router is not None:
            next_pid_comp_map = router.pid_sat_comp.get(next_pid, {})
            next_mgmt_comp_id = next_pid_comp_map.get(next_mgmt_sat)
        
        candidates_same_cc = []
        candidates_all = []
        
        for (u, v) in meta.get('isl_pairs', []):
            if sat_pid.get(u) == next_pid and sat_pid.get(v) == src_pid:
                u, v = v, u
            
            # 分量感知（來源側）
            if src_comp_id is not None and router is not None:
                pid_comp_map = router.pid_sat_comp.get(src_pid, {})
                u_comp_id = pid_comp_map.get(u)
                if u_comp_id != src_comp_id:
                    continue
            
            d = G_sat.get_edge_data(u, v, default={})
            geo_dist = float(d.get('geo_len_m', d.get('weight', 1.0)))
            
            # QUEUE-AWARE: 獲取 queue 狀態
            q_packets = 0
            if queue_packets:
                q_packets = queue_packets.get((u, v), queue_packets.get((v, u), 0))
            
            # 計算綜合成本 (距離 + queue 懲罰)
            total_cost = calculate_link_queue_cost(
                geo_dist, q_packets,
                alpha_dist=ALPHA_DISTANCE,
                alpha_queue=ALPHA_QUEUE,
                queue_norm_max=QUEUE_NORMALIZE_MAX_PACKETS,
                queue_max_penalty_m=QUEUE_MAX_PENALTY_M
            )
            
            # 分量感知（目標側）
            v_same_cc_as_mgmt = False
            if next_mgmt_comp_id is not None and router is not None:
                next_pid_comp_map = router.pid_sat_comp.get(next_pid, {})
                v_comp_id = next_pid_comp_map.get(v)
                if v_comp_id == next_mgmt_comp_id:
                    v_same_cc_as_mgmt = True
            
            if v_same_cc_as_mgmt:
                candidates_same_cc.append((total_cost, u, v))
            candidates_all.append((total_cost, u, v))
        
        # 優先從同 CC 候選中選擇
        if candidates_same_cc:
            candidates_same_cc.sort()
            _, u, v = candidates_same_cc[0]
            return (u, v)
        elif candidates_all:
            candidates_all.sort()
            _, u, v = candidates_all[0]
            return (u, v)
        
        return None


# ==========================
# 端到端 fstate 拼接 - Helper Functions
# ==========================

def _add_ecmp_perturbation(G: nx.Graph, eps: float = 1e-8) -> None:
    """為圖的所有邊添加極小擾動，消除 ECMP 平手問題"""
    for u, v, data in G.edges(data=True):
        edge_id = (min(u, v), max(u, v))
        random.seed(hash(edge_id) % (2**32))
        perturbation = random.random() * eps
        original_weight = data.get('weight', 1.0)
        data['weight_eff'] = original_weight + perturbation


def _build_potential_field(targets: List[int], G: nx.Graph, weight: str = 'weight_eff') -> Dict[int, float]:
    """
    建立勢能場：以目標節點為 source 計算到所有節點的最短距離
    
    Args:
        targets: 目標節點列表 (可能多個)
        G: NetworkX 圖
        weight: 邊權重屬性名稱 (預設 'weight_eff' 使用 ECMP 擾動後的權重)
    
    Returns:
        dist: {node_id: distance_to_nearest_target}
        
    多目標時取 min(dist_to_target_i)
    """
    dist = {n: float('inf') for n in G.nodes()}
    
    for target in targets:
        if target not in G:
            continue
        
        try:
            # 從目標反向計算距離（確保一致性）
            dist_from_target = nx.single_source_dijkstra_path_length(
                G, target, weight=weight
            )
            
            # 更新為最小距離
            for node, d in dist_from_target.items():
                dist[node] = min(dist[node], d)
        except nx.NetworkXError:
            # 目標不在圖中或其他錯誤
            continue
    
    return dist


def _select_potential_descent_neighbor(
    u: int, 
    neighbors: List[int], 
    dist: Dict[int, float], 
    tolerance: float = 1e-6
) -> Optional[int]:
    """
    選擇使勢能下降的鄰居（ECMP 一致性破平手）
    
    Args:
        u: 當前節點
        neighbors: ISL 鄰居列表
        dist: 勢能場 (distance to target)
        tolerance: 容忍度 (允許極小的「水平移動」)
    
    Returns:
        next_hop: 選中的鄰居 ID，若無法選擇則 None
    
    優先級:
        1. 嚴格下降: dist[n] < dist[u] - tolerance
        2. 弱下降: dist[n] <= dist[u] + tolerance
        3. 最小上升: min(dist[n]) where dist[n] > dist[u]
        4. 無法選擇: None (等待 holdover)
    """
    my_dist = dist.get(u, float('inf'))
    
    # 過濾掉距離為 inf 的鄰居（不可達）
    valid_neighbors = [n for n in neighbors if dist.get(n, float('inf')) < float('inf')]
    if not valid_neighbors:
        return None
    
    # 1. 嚴格下降
    strict_descent = [
        n for n in valid_neighbors
        if dist[n] < my_dist - tolerance
    ]
    if strict_descent:
        # ECMP 破平手：選 dist 最小，再選 id 最小
        return min(strict_descent, key=lambda n: (dist[n], n))
    
    # 2. 弱下降（容忍範圍內）
    weak_descent = [
        n for n in valid_neighbors
        if dist[n] <= my_dist + tolerance
    ]
    if weak_descent:
        return min(weak_descent, key=lambda n: (dist[n], n))
    
    # 3. 被迫上升（選上升最少的）
    # 這種情況理論上不應該發生在正確的勢能場中，但作為 fallback
    return min(valid_neighbors, key=lambda n: (dist[n], n))


def _route_direct_in_subgraph(src: int, dst: int, pid: int, 
                               router, G_sat: nx.Graph,
                               intra_tree_cache: Optional[Dict] = None) -> Optional[int]:
    """
    在 PID 子圖內，從 src 直接路由到 dst（優先使用預計算的路徑樹快取）
    
    注意：不處理 src==dst 的情況（應該在主流程攔截）
    
    Args:
        src: 源衛星 ID
        dst: 目標衛星 ID
        pid: PID ID
        router: VirtualPIDRouterPlaneBlock 實例
        G_sat: 衛星網絡圖
        intra_tree_cache: 預計算的群內路徑樹快取 {(dst, pid): {src: next_hop}}
    
    Returns:
        下一跳衛星 ID，或 None（失敗）
    """
    # ★ 性能優化：優先使用預計算的路徑樹快取
    if intra_tree_cache is not None:
        cache_key = (dst, pid)
        if cache_key in intra_tree_cache:
            next_hop_map = intra_tree_cache[cache_key]
            if src in next_hop_map:
                nh = next_hop_map[src]
                if G_sat.has_edge(src, nh):
                    return nh
    
    # 快取未命中，回退到原有邏輯（勢能場路由）
    
    # 檢查連通性
    comp_map = router.pid_sat_comp.get(pid, {})
    src_comp = comp_map.get(src)
    dst_comp = comp_map.get(dst)
    
    if src_comp is None or dst_comp is None or src_comp != dst_comp:
        return None
    
    # ★ 關鍵修復：不使用 router.pid_subgraphs（多線程競態），直接在 G_sat 上計算
    # 但只考慮該 PID 的節點
    pid_nodes = set(router.pid_members.get(pid, []))
    if src not in pid_nodes or dst not in pid_nodes:
        return None
    
    # 創建臨時子圖視圖（只包含該 PID 的節點）
    subgraph = G_sat.subgraph(pid_nodes)
    
    # 使用勢能場選擇下一跳（tolerance 對齊 ECMP 擾動）
    potential = _build_potential_field([dst], subgraph, weight='weight_eff')
    neighbors = list(G_sat.neighbors(src))  # 使用 G_sat 的鄰居（確保是當前拓撲）
    
    # 只考慮在同一 PID 內的鄰居
    neighbors = [n for n in neighbors if n in pid_nodes]
    
    if not neighbors:
        return None
    
    next_hop = _select_potential_descent_neighbor(
        src, neighbors, potential, tolerance=1e-8
    )
    
    return next_hop


def _fallback_spf_one_hop(src: int, dst: int, G_sat: nx.Graph) -> Optional[int]:
    """
    保底機制：在全網圖上計算到 dst 的 SPF，選擇能使距離下降的鄰居
    
    只選一步，不預先計算整條路徑
    
    Returns:
        下一跳衛星 ID，或 None（失敗）
    """
    if not G_sat.has_node(src) or not G_sat.has_node(dst):
        return None
    
    try:
        # 計算從 dst 到所有節點的距離（反向 Dijkstra）
        distances = nx.single_source_dijkstra_path_length(
            G_sat, dst, weight='weight_eff'
        )
        
        if src not in distances:
            return None
        
        src_dist = distances[src]
        neighbors = list(G_sat.neighbors(src))
        
        if not neighbors:
            return None
        
        # 找能縮短距離的鄰居
        candidates = []
        for neighbor in neighbors:
            if neighbor in distances:
                neighbor_dist = distances[neighbor]
                edge_weight = G_sat[src][neighbor].get('weight_eff', 1.0)
                # 檢查是否在最短路徑上
                if abs(src_dist - edge_weight - neighbor_dist) < 1e-6:
                    candidates.append(neighbor)
        
        # 確定性選擇：ID 最小的鄰居
        if candidates:
            return min(candidates)
        
        return None
    
    except Exception:
        return None


def _break_2cycles(
    fstate: Dict[Tuple[int,int], Tuple[int,int,int]],
    G_sat: nx.Graph,
    sat_pid: Dict[int,int],
    router,  # VirtualPIDRouterPlaneBlock
    num_sats: int,
    dst_sat_map: Dict[int,int],
    isl_if_idxs_func: Callable,
    log_debug_func: Callable,
    max_iterations: int = 3
) -> Dict[Tuple[int,int], Tuple[int,int,int]]:
    """
    作為保險機制，迭代檢測並修復 2-cycles (A ↔ B)
    
    Args:
        fstate: 當前轉發狀態
        G_sat: 衛星圖
        sat_pid: 衛星到群ID映射
        router: 路由器對象（用於獲取子圖）
        num_sats: 衛星總數
        dst_sat_map: 目的地到衛星映射
        isl_if_idxs_func: ISL interface 索引函數
        log_debug_func: 日誌函數
        max_iterations: 最大迭代次數
    
    Returns:
        修復後的 fstate
    
    策略:
        1. 檢測所有 2-cycles: (u, dst) → v, (v, dst) → u
        2. id 較大的改指向勢能下降的鄰居
        3. 若無勢能下降鄰居，設為 None（等待 holdover）
        4. 迭代直到無新 2-cycle 或達最大迭代次數
    """
    for iteration in range(max_iterations):
        cycles_found = []
        
        # 檢測所有 2-cycles
        checked = set()
        for (u, dst), (next_hop, my_if, next_if) in fstate.items():
            if (u, dst) in checked:
                continue
            
            # 檢查是否形成 2-hop loop
            reverse_entry = fstate.get((next_hop, dst))
            if reverse_entry is not None:
                reverse_next = reverse_entry[0]
                if reverse_next == u:
                    # 發現 2-cycle: u ↔ next_hop
                    smaller_id = min(u, next_hop)
                    larger_id = max(u, next_hop)
                    cycles_found.append((smaller_id, larger_id, dst))
                    checked.add((u, dst))
                    checked.add((next_hop, dst))
        
        # ★ 性能優化：如果本輪沒有發現 2-cycle，提前終止
        if not cycles_found:
            # log_debug_func(f"  2-Cycle 清洗第 {iteration+1} 輪：無發現，提前終止")
            break
        
        # 修復: id 較大的改指向勢能下降的鄰居
        fixes_applied = 0
        for (small_id, large_id, dst) in cycles_found:
            # 獲取 large_id 所在的群
            large_pid = sat_pid.get(large_id)
            if large_pid is None:
                continue
            
            # 獲取目標衛星
            dst_sat = dst if dst < num_sats else dst_sat_map.get(dst)
            if dst_sat is None:
                continue
            
            # 建立勢能場
            pid_nodes = set(router.pid_members.get(large_pid, []))
            if large_id not in pid_nodes:
                continue
            
            subgraph = G_sat.subgraph(pid_nodes)
            potential_dist = _build_potential_field([dst_sat], subgraph, weight='weight_eff')
            
            # ★ 改進：先嘗試同 PID 鄰居，若無法修復則允許任何鄰居
            neighbors_in_pid = [n for n in G_sat.neighbors(large_id) if n != small_id and n in pid_nodes]
            new_hop = _select_potential_descent_neighbor(large_id, neighbors_in_pid, potential_dist, tolerance=1e-6)
            
            # 若同 PID 無法修復，使用全局勢能場嘗試任意鄰居
            if new_hop is None:
                global_potential_dist = _build_potential_field([dst_sat], G_sat, weight='weight_eff')
                all_neighbors = [n for n in G_sat.neighbors(large_id) if n != small_id]
                new_hop = _select_potential_descent_neighbor(large_id, all_neighbors, global_potential_dist, tolerance=1e-6)
            
            if new_hop is not None:
                # 成功找到替代路徑
                my_if, next_if = isl_if_idxs_func(large_id, new_hop)
                fstate[(large_id, dst)] = (new_hop, my_if, next_if)
                fixes_applied += 1
            else:
                # 無法修復，移除等待 holdover
                if (large_id, dst) in fstate:
                    del fstate[(large_id, dst)]
                    fixes_applied += 1
        
        # log_debug_func(f"  2-Cycle 清洗第 {iteration+1} 輪：發現 {len(cycles_found)} 個，修復 {fixes_applied} 個")
    
    return fstate


# ==========================
# 主要 fstate 建構函數
# ==========================
def build_fstate_lhtr(
    G_sat: nx.Graph,
    sat_pid: Dict[int,int],
    router: VirtualPIDRouterPlaneBlock,
    gplanner: GroupPlanner,
    ground_station_satellites_in_range,
    satellites,
    ground_stations,
    num_isls_per_sat,
    gid_to_sat_gsl_if_idx,
    prev_dst_sat_map: Optional[Dict[int,int]] = None,
    prev_src_sat_map: Optional[Dict[int,int]] = None,
    prev_fstate: Optional[Dict[Tuple[int,int], Tuple[int,int,int]]] = None,
    queue_packets: Optional[Dict[Tuple[int,int], int]] = None,
) -> Tuple[
    Dict[Tuple[int,int], Tuple[int,int,int]],
    Dict[int,int],
    Dict[int,int],
    Dict[str, int],
    Dict[str, int],
]:
    """
    QUEUE-AWARE: 產生 fstate（第一跳）：(u,dst) -> (next_hop, my_if, next_if)
    
    新增：
    - queue_packets: 用於 queue-aware 邊界選擇
    
    基於 algorithm_lohi_kun.py 的 build_fstate_lohi，保留完整階層路由邏輯
    """
    num_sats = len(satellites) if not isinstance(satellites,int) else satellites
    num_gs = len(ground_stations) if not isinstance(ground_stations,int) else ground_stations

    # 應用 ECMP 擾動
    _add_ecmp_perturbation(G_sat, eps=1e-8)

    reason = Counter()
    missing_reason: Dict[Tuple[int, int], str] = {}

    def _record_missing(src: int, dst: int, why: str) -> None:
        reason[why] += 1
        missing_reason[(src, dst)] = why

    def _record_write(src: int, dst: int, decision: Tuple[int, int, int], why: str = "written_successfully") -> None:
        fstate[(src, dst)] = decision
        reason[why] += 1
        missing_reason.pop((src, dst), None)

    # 目的集合：將每個 GS 投影到其候選可視衛星所在 PID
    dst_pid_map: Dict[int,int] = {}
    dst_sat_map: Dict[int,int] = {}
    src_sat_map: Dict[int,int] = {}
    
    for gid0 in range(num_gs):
        candidates = ground_station_satellites_in_range.get(gid0, []) if isinstance(ground_station_satellites_in_range, dict) else []
        
        if not candidates:
            # GS 視線 fallback
            gs_node = num_sats + gid0
            if prev_dst_sat_map and gs_node in prev_dst_sat_map:
                fallback_sat = prev_dst_sat_map[gs_node]
                if fallback_sat in sat_pid:
                    dst_pid_map[gs_node] = sat_pid[fallback_sat]
                    dst_sat_map[gs_node] = fallback_sat
                    reason["dst_projection_prev"] += 1
                    continue
            
            fallback_sat = gid0 % num_sats
            if fallback_sat in sat_pid:
                dst_pid_map[gs_node] = sat_pid[fallback_sat]
                dst_sat_map[gs_node] = fallback_sat
                reason["dst_projection_gid_mod"] += 1
            continue
        
        sat_candidate = candidates[0][1] if isinstance(candidates[0], (list,tuple)) and len(candidates[0])>1 else candidates[0]
        if sat_candidate in sat_pid:
            dst_pid_map[num_sats + gid0] = sat_pid[sat_candidate]
            dst_sat_map[num_sats + gid0] = sat_candidate
            reason["dst_projection_visible"] += 1

    # 嘗試取得鄰接介面索引查表
    global _SAT_NEI_TO_IF
    sat_neighbor_to_if = globals().get('_SAT_NEI_TO_IF', None)

    def _isl_if_idxs(u:int, v:int) -> Tuple[int,int]:
        """回傳 u→v 的 (my_if, next_if)"""
        if sat_neighbor_to_if is not None:
            try:
                return int(sat_neighbor_to_if[(u, v)]), int(sat_neighbor_to_if[(v, u)])
            except Exception:
                pass
        d = G_sat.get_edge_data(u, v, default={}) or {}
        cand_u = d.get('if_u', d.get('if_idx_u', d.get('if_idx_src')))
        cand_v = d.get('if_v', d.get('if_idx_v', d.get('if_idx_dst')))
        mu = int(cand_u) if cand_u is not None else 0
        mv = int(cand_v) if cand_v is not None else 0
        if num_isls_per_sat and len(num_isls_per_sat) > u and num_isls_per_sat[u] > 0:
            mu %= num_isls_per_sat[u]
        if num_isls_per_sat and len(num_isls_per_sat) > v and num_isls_per_sat[v] > 0:
            mv %= num_isls_per_sat[v]
        return mu, mv
    
    # 目的群為根：快取 prev map，確保全網一致的下一個群決策
    dst_pid_prev_cache: Dict[int, Dict[int,int]] = {}
    # **群內最短路樹快取**：(dst_sat, src_pid) -> {sat_id: next_hop_sat_id}
    intra_group_tree_cache: Dict[Tuple[int,int], Dict[int,int]] = {}
    
    EPS = 1e-4
    
    fstate: Dict[Tuple[int,int], Tuple[int,int,int]] = {}

    # 控制面職責 1️⃣：群間路由決策（Group-level SPF）
    pid_to_group_path = {}
    
    for gid in range(num_gs):
        dst_node = num_sats + gid
        if dst_node not in dst_pid_map:
            reason["dst_pid_missing"] += 1
            continue
        
        dst_pid = dst_pid_map[dst_node]
        
        if dst_pid not in pid_to_group_path:
            dist, prev = gplanner.distances_to(dst_pid)
            pid_to_group_path[dst_pid] = (dist, prev)
    
    # 🚀 性能優化：預計算群內路徑樹（避免重複 SPF）
    unique_dst_targets = {}
    for dst_node, dst_sat in dst_sat_map.items():
        dst_pid = sat_pid.get(dst_sat)
        if dst_pid is not None:
            unique_dst_targets[dst_sat] = dst_pid
    
    for dst_sat, dst_pid in unique_dst_targets.items():
        cache_key = (dst_sat, dst_pid)
        if cache_key in intra_group_tree_cache:
            continue
        
        Gp = router.pid_subgraphs.get(dst_pid)
        if not Gp or not Gp.has_node(dst_sat):
            reason["intra_tree_missing"] += 1
            continue
        
        try:
            lengths, paths = nx.single_source_dijkstra(Gp, dst_sat, weight='weight')
            
            next_hop_map = {}
            for src_node, path in paths.items():
                if src_node == dst_sat:
                    continue
                if len(path) >= 2:
                    # path is [dst_sat, ..., src_node] from single_source_dijkstra(dst_sat)
                    next_hop_map[src_node] = path[-2]
            
            intra_group_tree_cache[cache_key] = next_hop_map
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            pass
    
    # 對每個源衛星 → 目標 GS 進行路由
    for u in range(num_sats):
        src_pid = sat_pid.get(u)
        if src_pid is None:
            reason["src_pid_none"] += 1
            continue
        
        for gid in range(num_gs):
            dst_node = num_sats + gid
            if dst_node not in dst_sat_map:
                _record_missing(u, dst_node, "dst_sat_missing")
                continue
            
            dst_sat = dst_sat_map[dst_node]
            dst_pid = sat_pid.get(dst_sat)
            if dst_pid is None:
                _record_missing(u, dst_node, "dst_pid_none")
                continue
            
            # 特殊情況：已經在目標衛星
            if u == dst_sat:
                gsl_if_idx = gid_to_sat_gsl_if_idx[gid] if gid_to_sat_gsl_if_idx and gid < len(gid_to_sat_gsl_if_idx) else 0
                my_if = num_isls_per_sat[u] + gsl_if_idx if num_isls_per_sat and u < len(num_isls_per_sat) else gsl_if_idx
                _record_write(u, dst_node, (dst_node, my_if, 0), "written_same_sat_to_gs")
                continue
            
            # 情況 A: 同群路由
            if src_pid == dst_pid:
                mgmt_sat = router.pid_mgmt_sat.get(src_pid)
                comp_map = router.pid_sat_comp.get(src_pid, {})
                u_comp = comp_map.get(u)
                dst_comp = comp_map.get(dst_sat)
                mgmt_comp = comp_map.get(mgmt_sat) if mgmt_sat else None
                
                # 決定目標
                target = None
                if u == mgmt_sat:
                    target = dst_sat
                elif (ENFORCE_MGMT_HOP_SAME_PID and mgmt_sat is not None and 
                      u_comp == mgmt_comp == dst_comp):
                    target = mgmt_sat
                else:
                    target = dst_sat
                
                # 在群內路由
                next_hop = _route_direct_in_subgraph(u, target, src_pid, router, G_sat, intra_group_tree_cache)
                
                # 保底機制
                if next_hop is None:
                    next_hop = _fallback_spf_one_hop(u, dst_sat, G_sat)
                
                # ISL驗證
                if next_hop is not None and G_sat.has_edge(u, next_hop):
                    my_if, next_if = _isl_if_idxs(u, next_hop)
                    _record_write(u, dst_node, (next_hop, my_if, next_if), "written_successfully")
                elif next_hop is None:
                    _record_missing(u, dst_node, "route_none")
                else:
                    _record_missing(u, dst_node, "fallback_failed")
                continue
            
            # 情況 B: 跨群路由
            dist, prev = pid_to_group_path.get(dst_pid, ({}, {}))
            next_pid = prev.get(src_pid)
            
            if next_pid is None:
                _record_missing(u, dst_node, "next_pid_none")
                continue
            
            # QUEUE-AWARE: 邊界衛星對選擇（傳入 queue_packets）
            border_pair = BorderSelector.pick_border_pair(
                G_sat, gplanner, src_pid, next_pid, sat_pid,
                src_sat=u, router=router, queue_packets=queue_packets
            )
            
            if not border_pair:
                _record_missing(u, dst_node, "border_none")
                continue
            
            u_border, v_border = border_pair
            u_border2, v_border2 = None, None
            
            # B1. 硬規則：邊界直接跳轉
            if u == u_border:
                # 1. 嘗試主邊界
                if G_sat.has_edge(u_border, v_border):
                    my_if, next_if = _isl_if_idxs(u_border, v_border)
                    _record_write(u, dst_node, (v_border, my_if, next_if), "written_successfully")
                    continue
                
                # 2. 嘗試次佳邊界
                if u_border2 and v_border2:
                    if u == u_border2 and G_sat.has_edge(u_border2, v_border2):
                        my_if, next_if = _isl_if_idxs(u_border2, v_border2)
                        _record_write(u, dst_node, (v_border2, my_if, next_if), "written_successfully")
                        continue
                    else:
                        next_hop = _route_direct_in_subgraph(u, u_border2, src_pid, router, G_sat, intra_group_tree_cache)
                        if next_hop and G_sat.has_edge(u, next_hop):
                            my_if, next_if = _isl_if_idxs(u, next_hop)
                            _record_write(u, dst_node, (next_hop, my_if, next_if), "written_successfully")
                            continue
                
                # 3. 嘗試管理中繼
                mgmt_sat = router.pid_mgmt_sat.get(src_pid)
                if ENFORCE_MGMT_HOP_CROSS_PID and mgmt_sat:
                    comp_map = router.pid_sat_comp.get(src_pid, {})
                    if comp_map.get(u) == comp_map.get(mgmt_sat):
                        next_hop = _route_direct_in_subgraph(u, mgmt_sat, src_pid, router, G_sat, intra_group_tree_cache)
                        if next_hop and G_sat.has_edge(u, next_hop):
                            my_if, next_if = _isl_if_idxs(u, next_hop)
                            _record_write(u, dst_node, (next_hop, my_if, next_if), "written_successfully")
                            continue
                
                # 4. SPF 保底
                fallback_target = u_border2 if u_border2 else u_border
                next_hop = _fallback_spf_one_hop(u, fallback_target, G_sat)
                if next_hop and G_sat.has_edge(u, next_hop):
                    my_if, next_if = _isl_if_idxs(u, next_hop)
                    _record_write(u, dst_node, (next_hop, my_if, next_if), "written_successfully")
                    continue
                
                # 5. 條件式 holdover
                if prev_fstate and (u, dst_node) in prev_fstate:
                    prev_entry = prev_fstate[(u, dst_node)]
                    prev_next_hop = prev_entry[0]
                    if G_sat.has_edge(u, prev_next_hop):
                        _record_write(u, dst_node, prev_entry, "holdover")
                        continue
                _record_missing(u, dst_node, "fallback_failed")
                continue
            
            # B2. 資料面：非邊界衛星直接往邊界路由
            next_hop = _route_direct_in_subgraph(u, u_border, src_pid, router, G_sat, intra_group_tree_cache)
            
            # 保底機制
            if next_hop is None:
                next_hop = _fallback_spf_one_hop(u, u_border, G_sat)
            
            # ISL驗證
            if next_hop is not None and G_sat.has_edge(u, next_hop):
                my_if, next_if = _isl_if_idxs(u, next_hop)
                _record_write(u, dst_node, (next_hop, my_if, next_if), "written_successfully")
            elif next_hop is None:
                _record_missing(u, dst_node, "route_none")
            else:
                _record_missing(u, dst_node, "fallback_failed")

    # Ground stations to ground stations
    for src_gid in range(num_gs):
        src_gs_node = num_sats + src_gid
        
        src_candidates = ground_station_satellites_in_range.get(src_gid, []) if isinstance(ground_station_satellites_in_range, dict) else []
        
        if src_candidates:
            src_sat = src_candidates[0][1] if isinstance(src_candidates[0], (list,tuple)) and len(src_candidates[0])>1 else src_candidates[0]
        elif prev_src_sat_map and src_gs_node in prev_src_sat_map:
            src_sat = prev_src_sat_map[src_gs_node]
            if src_sat not in sat_pid:
                src_sat = src_gid % num_sats
        else:
            src_sat = src_gid % num_sats
        
        src_sat_map[src_gs_node] = src_sat
        
        for dst_gid in range(num_gs):
            if src_gid == dst_gid:
                continue
            dst_gs_node = num_sats + dst_gid
            my_if = 0
            next_if = num_isls_per_sat[src_sat] + gid_to_sat_gsl_if_idx[src_gid] if num_isls_per_sat else 0
            _record_write(src_gs_node, dst_gs_node, (src_sat, my_if, next_if), "written_gs_to_gs")
    
    # 2-Cycle 清洗
    def _noop_log(msg):
        pass
    
    fstate = _break_2cycles(fstate, G_sat, sat_pid, router, num_sats, dst_sat_map, _isl_if_idxs, _noop_log, max_iterations=3)

    # Ensure complete SAT->GS coverage with explicit drop entries.
    missing_before_fill = 0
    for u in range(num_sats):
        for gid in range(num_gs):
            dst_node = num_sats + gid
            if (u, dst_node) not in fstate:
                missing_before_fill += 1
                _record_write(u, dst_node, (-1, -1, -1), "drop_filled")
                if (u, dst_node) not in missing_reason:
                    missing_reason[(u, dst_node)] = "drop_filled"

    reason["missing_before_drop_fill"] = missing_before_fill
    reason["written_successfully_total"] = len(fstate)
    reason["written_successfully"] = (
        reason.get("written_successfully", 0)
        + reason.get("written_same_sat_to_gs", 0)
        + reason.get("written_gs_to_gs", 0)
    )
    reason["sat_to_gs_expected"] = num_sats * num_gs
    reason["sat_to_gs_present"] = sum(1 for (src, _dst) in fstate.keys() if src < num_sats)

    return fstate, dst_sat_map, src_sat_map, dict(reason), dict(Counter(missing_reason.values()))


# ==========================
# Hypatia adapter
# ==========================
_ROUTER: Optional[VirtualPIDRouterPlaneBlock] = None
_GPLANNER: Optional[GroupPlanner] = None
_PREV_DST_SAT_MAP: Dict[int,int] = {}
_PREV_SRC_SAT_MAP: Dict[int,int] = {}


def init(config: Optional[dict] = None):
    """初始化 LHTR 模組"""
    global BETA_Q, BETA_S
    global _ROUTER, _GPLANNER

    cfg = config or {}
    BETA_Q = float(cfg.get('beta_q', BETA_Q))
    BETA_S = float(cfg.get('beta_s', BETA_S))

    planes_per_group = cfg.get('planes_per_group', PLANES_PER_GROUP)
    sats_per_plane = cfg.get('sats_per_plane_in_group', SATS_PER_PLANE_IN_GROUP)
    
    _ROUTER = VirtualPIDRouterPlaneBlock(
        M_down=2,
        planes_per_group=planes_per_group,
        sats_per_plane_in_group=sats_per_plane
    )
    _GPLANNER = GroupPlanner()
    
    _get_process_local_stats().reset()
    
    return {'ok': True, 'msg': f'algorithm_lhtr initialized with p={planes_per_group}, s={sats_per_plane}'}


# Version guard for pickle compatibility
_LHTR_STATE_VERSION = 1


def save_lhtr_state(filepath: str) -> bool:
    """Save _ROUTER, _GPLANNER, _PREV_DST_SAT_MAP, _PREV_SRC_SAT_MAP to a pickle file.

    Returns True on success, False on failure.
    """
    import pickle as _pkl
    try:
        payload = {
            'version': _LHTR_STATE_VERSION,
            'router': _ROUTER,
            'gplanner': _GPLANNER,
            'prev_dst_sat_map': _PREV_DST_SAT_MAP,
            'prev_src_sat_map': _PREV_SRC_SAT_MAP,
        }
        with open(filepath, 'wb') as f:
            _pkl.dump(payload, f, protocol=_pkl.HIGHEST_PROTOCOL)
        print("  > [LHTR] Saved state → %s" % filepath)
        return True
    except Exception as e:
        print("  > [LHTR] WARNING: Failed to save state: %s" % e)
        return False


def load_lhtr_state(filepath: str) -> bool:
    """Load _ROUTER, _GPLANNER, _PREV_DST_SAT_MAP, _PREV_SRC_SAT_MAP from pickle.

    On success sets the module globals and returns True.
    On any failure (missing file, version mismatch, unpickle error) returns False
    and leaves the globals untouched so the caller can fall back to init().
    """
    import pickle as _pkl
    global _ROUTER, _GPLANNER, _PREV_DST_SAT_MAP, _PREV_SRC_SAT_MAP

    if not os.path.exists(filepath):
        print("  > [LHTR] No state file: %s" % filepath)
        return False
    try:
        with open(filepath, 'rb') as f:
            payload = _pkl.load(f)
        if not isinstance(payload, dict) or payload.get('version') != _LHTR_STATE_VERSION:
            print("  > [LHTR] Version mismatch or corrupt state file, ignoring")
            return False
        r = payload.get('router')
        g = payload.get('gplanner')
        if not isinstance(r, VirtualPIDRouterPlaneBlock) or not isinstance(g, GroupPlanner):
            print("  > [LHTR] Invalid object types in state file, ignoring")
            return False
        _ROUTER = r
        _GPLANNER = g
        _PREV_DST_SAT_MAP = payload.get('prev_dst_sat_map', {})
        _PREV_SRC_SAT_MAP = payload.get('prev_src_sat_map', {})
        print("  > [LHTR] Restored state from %s (stable_edges=%d)"
              % (filepath, len(_GPLANNER.stable_edges)))
        return True
    except Exception as e:
        print("  > [LHTR] WARNING: Failed to load state: %s" % e)
        return False


def algorithm_lhtr(
    output_dynamic_state_dir,
    time_since_epoch_ns,
    satellites,
    ground_stations,
    sat_net_graph_only_satellites_with_isls,
    ground_station_satellites_in_range,
    num_isls_per_sat,
    sat_neighbor_to_if,
    list_gsl_interfaces_info,
    prev_output,
    enable_verbose_logs,
    # QUEUE-AWARE: 新增參數 (都有預設值，向後相容)
    queue_stats_file: Optional[str] = None,  # QUEUE-AWARE: CSV 檔案路徑
    link_queue_bytes: Optional[Dict[Tuple[int,int], int]] = None,
    link_rate_bps: Optional[Dict[Tuple[int,int], float]] = None,
    time_step_ns: Optional[int] = None,
    group_cost_mode: str = 'hop',
):
    """
    LHTR (Load-aware Hierarchical Traffic Routing) Algorithm
    
    基於 LoHi 的 queue-aware 階層式路由
    
    新增參數：
        queue_stats_file: NS-3 輸出的 queue 統計 CSV 檔案路徑
        其他參數與 LoHi 相同，保持向後相容
    """
    global _PREV_DST_SAT_MAP, _PREV_SRC_SAT_MAP, _SAT_NEI_TO_IF
    
    assert _ROUTER is not None and _GPLANNER is not None, "call init() first"

    assert time_step_ns is not None
    step_ns = int(time_step_ns)
    snapshot_idx = int(time_since_epoch_ns // step_ns)
    step_ms = int(step_ns // 1_000_000)
    _ROUTER.set_snapshot(snapshot_idx, step_ms)
    _GPLANNER.set_snapshot(snapshot_idx, step_ms)

    if enable_verbose_logs:
        print(f"\n{'='*70}")
        print(f"LHTR Algorithm at t={time_since_epoch_ns} ns (snapshot {snapshot_idx})")
        print(f"{'='*70}")

    num_sats = len(satellites) if not isinstance(satellites, int) else satellites
    
    # 重置權重
    for _, _, d in sat_net_graph_only_satellites_with_isls.edges(data=True):
        if 'geo_len_m' in d:
            d['weight'] = d['geo_len_m']
    
    # Chaos Monkey
    if ENABLE_CHAOS_MONKEY and (snapshot_idx % CHAOS_INTERVAL_SNAPSHOTS == 0):
        removed_isls = chaos_monkey_inject_failures(
            sat_net_graph_only_satellites_with_isls, 
            snapshot_idx, 
            CHAOS_FAILURE_RATE,
            CHAOS_LOG_FILE
        )
        if enable_verbose_logs:
            print(f"  > [CHAOS_MONKEY] Injected {len(removed_isls)} ISL failures")
    
    # 添加衛星屬性
    constellation_config = _infer_constellation_config(num_sats)
    
    for sid in range(num_sats):
        node_data = sat_net_graph_only_satellites_with_isls.nodes.get(sid, None)
        if node_data is None:
            sat_net_graph_only_satellites_with_isls.add_node(sid)
            node_data = sat_net_graph_only_satellites_with_isls.nodes[sid]
        
        if constellation_config:
            num_orbits, num_sats_per_orbit = constellation_config
            orbit = sid // num_sats_per_orbit
            pos = sid % num_sats_per_orbit
            node_data['plane'] = orbit
            node_data['pos_in_plane'] = pos

    # 分群
    sat_ids = list(range(num_sats))
    sat_to_pid = _ROUTER.refresh_pid_members_and_subgraphs(sat_ids,
                                                           sat_net_graph_only_satellites_with_isls)

    # QUEUE-AWARE: 讀取 queue 統計
    queue_packets = {}
    if queue_stats_file:
        queue_packets = load_queue_statistics_from_csv(queue_stats_file, num_sats, enable_verbose_logs)
        if enable_verbose_logs and queue_packets:
            print(f"  > [QUEUE-AWARE] Loaded {len(queue_packets)} queue entries from {queue_stats_file}")

    # QUEUE-AWARE: 群內權重更新 (使用增強模式)
    apply_queue_aware_weights_intra_only(sat_net_graph_only_satellites_with_isls,
                                         sat_to_pid,
                                         link_queue_bytes,
                                         link_rate_bps,
                                         queue_packets=queue_packets,
                                         beta_q=BETA_Q, 
                                         beta_s=BETA_S,
                                         use_enhanced_queue_cost=True)

    # 建立群圖
    _GPLANNER.build_group_graph(sat_net_graph_only_satellites_with_isls,
                                sat_to_pid, cost_mode=group_cost_mode)

    # 正規化 GS 範圍
    gs_map = _normalize_gs_range_candidates(ground_station_satellites_in_range,
                                            satellites, ground_stations)
    
    num_ground_stations = len(ground_stations) if not isinstance(ground_stations, int) else ground_stations
    gid_to_sat_gsl_if_idx = [0] * num_ground_stations
    
    prev_fstate = None
    if prev_output is not None and 'fstate' in prev_output:
        prev_fstate = prev_output['fstate']
    
    # 設定全局變數供 build_fstate_lhtr 使用
    _SAT_NEI_TO_IF = sat_neighbor_to_if
    
    # QUEUE-AWARE: 生成 fstate (傳入 queue_packets)
    fstate, dst_sat_map, src_sat_map, reason_counters, missing_reason_counts = build_fstate_lhtr(
        sat_net_graph_only_satellites_with_isls,
        sat_to_pid,
        _ROUTER,
        _GPLANNER,
        gs_map,
        satellites,
        ground_stations,
        num_isls_per_sat,
        gid_to_sat_gsl_if_idx,
        prev_dst_sat_map=_PREV_DST_SAT_MAP,
        prev_src_sat_map=_PREV_SRC_SAT_MAP,
        prev_fstate=prev_fstate,
        queue_packets=queue_packets,  # QUEUE-AWARE: 傳入 queue 資訊
    )
    if enable_verbose_logs:
        _dump_pid_snapshot(
            snapshot_idx,
            step_ms,
            _ROUTER,
            _GPLANNER,
            sat_to_pid,
            reason_counters=reason_counters,
            missing_reason_counts=missing_reason_counts,
        )
    
    _PREV_DST_SAT_MAP = dst_sat_map
    _PREV_SRC_SAT_MAP = src_sat_map
    
    # HOLDOVER 機制
    if prev_fstate:
        holdover_count = 0
        holdover_skipped = 0
        holdover_gsl_skipped = 0
        for (src, dst), decision in list(prev_fstate.items()):
            if (src, dst) not in fstate:
                next_hop = decision[0]
                if src < num_sats and next_hop < num_sats:
                    if sat_net_graph_only_satellites_with_isls.has_edge(src, next_hop):
                        fstate[(src, dst)] = decision
                        holdover_count += 1
                    else:
                        holdover_skipped += 1
                else:
                    # SAT->GS holdover must still be in current GS visibility set.
                    if src < num_sats and next_hop >= num_sats:
                        gid0 = dst - num_sats
                        if 0 <= gid0 < num_ground_stations:
                            candidates = gs_map.get(gid0, [])
                            sat_in_range = False
                            for cand in candidates:
                                sat_id = cand[1] if isinstance(cand, (list, tuple)) and len(cand) > 1 else cand
                                if sat_id == src:
                                    sat_in_range = True
                                    break
                            if not sat_in_range:
                                holdover_gsl_skipped += 1
                                continue
                    fstate[(src, dst)] = decision
                    holdover_count += 1
        
        reason_counters["holdover"] = reason_counters.get("holdover", 0) + holdover_count
        reason_counters["holdover_skipped_isl"] = reason_counters.get("holdover_skipped_isl", 0) + holdover_skipped
        reason_counters["holdover_skipped_gsl"] = reason_counters.get("holdover_skipped_gsl", 0) + holdover_gsl_skipped

        if enable_verbose_logs and holdover_count > 0:
            print(f"  > [HOLDOVER] Carried over {holdover_count} entries, skipped {holdover_skipped} ISL + {holdover_gsl_skipped} GSL")
    
    # ==================== 全局 SPF FALLBACK（改進 10 & 12）====================
    # 收集所有缺失的路由（沒有在 build_fstate_lhtr 中填充的）
    missing_routes = []
    for u in range(num_sats):
        for gid0 in range(num_ground_stations):
            dst_node = num_sats + gid0
            if (u, dst_node) not in fstate:
                missing_routes.append((u, dst_node, gid0))
    
    if enable_verbose_logs and len(missing_routes) > 0:
        print(f"  > Global fallback: {len(missing_routes)} missing routes (out of {num_sats * num_ground_stations} total)")
    
    if missing_routes:
        # 批次 SPF - 每個目標衛星只計算一次
        target_sats = {}
        
        for u, dst_node, gid0 in missing_routes:
            # 找到目標 GS 的可視衛星
            if dst_node in dst_sat_map:
                dst_sat = dst_sat_map[dst_node]
            elif gid0 in gs_map:
                candidates = gs_map[gid0]
                if candidates:
                    dst_sat = candidates[0][1] if isinstance(candidates[0], (list, tuple)) else candidates[0]
                else:
                    continue
            else:
                continue
            
            if dst_sat not in target_sats:
                target_sats[dst_sat] = []
            target_sats[dst_sat].append((u, dst_node, gid0))
        
        # 使用正確的接口索引計算
        def simple_isl_if_idx(u, v, G):
            """使用 sat_neighbor_to_if 確保接口 ID 正確"""
            if sat_neighbor_to_if is not None:
                try:
                    return int(sat_neighbor_to_if[(u, v)]), int(sat_neighbor_to_if[(v, u)])
                except Exception:
                    pass
            # Fallback: 從圖的邊屬性讀取
            if not G.has_edge(u, v):
                return 0, 0
            d = G.get_edge_data(u, v, default={}) or {}
            cand_u = d.get('if_u', d.get('if_idx_u', d.get('if_idx_src')))
            cand_v = d.get('if_v', d.get('if_idx_v', d.get('if_idx_dst')))
            mu = int(cand_u) if cand_u is not None else 0
            mv = int(cand_v) if cand_v is not None else 0
            if num_isls_per_sat and len(num_isls_per_sat) > u and num_isls_per_sat[u] > 0:
                mu %= num_isls_per_sat[u]
            if num_isls_per_sat and len(num_isls_per_sat) > v and num_isls_per_sat[v] > 0:
                mv %= num_isls_per_sat[v]
            return mu, mv
        
        # 對每個目標衛星執行一次 single_source_dijkstra
        if enable_verbose_logs:
            print(f"  > Computing global SPF for {len(target_sats)} unique target satellites...")
        
        for dst_sat, routes in target_sats.items():
            if not sat_net_graph_only_satellites_with_isls.has_node(dst_sat):
                continue
            
            try:
                lengths, paths = nx.single_source_dijkstra(
                    sat_net_graph_only_satellites_with_isls, 
                    dst_sat, 
                    weight='weight'
                )
                
                skipped_due_to_no_isl = 0
                filled_count = 0
                for u, dst_node, gid0 in routes:
                    if u in paths:
                        path = paths[u]
                        if len(path) >= 2:
                            next_hop = path[-2]
                            if sat_net_graph_only_satellites_with_isls.has_edge(u, next_hop):
                                my_if, next_if = simple_isl_if_idx(u, next_hop, sat_net_graph_only_satellites_with_isls)
                                fstate[(u, dst_node)] = (next_hop, my_if, next_if)
                                filled_count += 1
                            else:
                                skipped_due_to_no_isl += 1
                
                if enable_verbose_logs and skipped_due_to_no_isl > 0:
                    print(f"    [WARN] Skipped {skipped_due_to_no_isl} routes for dst_sat={dst_sat} (no ISL). Filled: {filled_count}")
                
            except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
                pass

    if enable_verbose_logs:
        reason_counters["global_fallback_missing_routes"] = len(missing_routes)

    # ==================== 最終 2-CYCLE 清理 ====================
    if enable_verbose_logs:
        print("  > Final 2-cycle cleanup after Holdover and Global fallback...")
    
    def final_isl_if_idxs(u: int, v: int) -> tuple:
        """使用 sat_neighbor_to_if 確保接口 ID 正確"""
        if sat_neighbor_to_if is not None:
            try:
                return int(sat_neighbor_to_if[(u, v)]), int(sat_neighbor_to_if[(v, u)])
            except Exception:
                pass
        # Fallback: 從圖的邊屬性讀取
        G = sat_net_graph_only_satellites_with_isls
        if not G.has_edge(u, v):
            return 0, 0
        d = G.get_edge_data(u, v, default={}) or {}
        cand_u = d.get('if_u', d.get('if_idx_u', d.get('if_idx_src')))
        cand_v = d.get('if_v', d.get('if_idx_v', d.get('if_idx_dst')))
        mu = int(cand_u) if cand_u is not None else 0
        mv = int(cand_v) if cand_v is not None else 0
        if num_isls_per_sat and len(num_isls_per_sat) > u and num_isls_per_sat[u] > 0:
            mu %= num_isls_per_sat[u]
        if num_isls_per_sat and len(num_isls_per_sat) > v and num_isls_per_sat[v] > 0:
            mv %= num_isls_per_sat[v]
        return mu, mv
    
    fstate = _break_2cycles(
        fstate, 
        sat_net_graph_only_satellites_with_isls, 
        sat_to_pid, 
        _ROUTER, 
        num_sats, 
        dst_sat_map, 
        final_isl_if_idxs,
        lambda *args, **kwargs: None,
        max_iterations=20
    )
    
    # 寫入 fstate
    output_filename = output_dynamic_state_dir + "/fstate_" + str(time_since_epoch_ns) + ".txt"
    changed_entries = 0
    total_entries = len(fstate)
    
    with open(output_filename, "w+") as f_out:
        for (src, dst), (nxt, my_if, next_if) in sorted(fstate.items()):
            prev_entry = prev_fstate.get((src, dst)) if prev_fstate else None
            new_entry = (nxt, my_if, next_if)
            
            if new_entry != prev_entry:
                f_out.write(f"{src},{dst},{nxt},{my_if},{next_if}\n")
                changed_entries += 1
    
    # 記錄路由更新統計
    _get_process_local_stats().record_routing_update(
        snapshot_idx, 
        step_ms * snapshot_idx, 
        changed_entries, 
        total_entries
    )
    
    # 寫入 GSL bandwidth
    bw_filename = output_dynamic_state_dir + "/gsl_if_bandwidth_" + str(time_since_epoch_ns) + ".txt"
    with open(bw_filename, "w+") as f_out:
        if time_since_epoch_ns == 0:
            for node_id in range(num_sats):
                f_out.write(f"{node_id},{num_isls_per_sat[node_id]},{list_gsl_interfaces_info[node_id]['aggregate_max_bandwidth']}\n")
            for node_id in range(num_sats, num_sats + num_ground_stations):
                f_out.write(f"{node_id},0,{list_gsl_interfaces_info[node_id]['aggregate_max_bandwidth']}\n")

    if enable_verbose_logs:
        print(f"  > Routing entries: {total_entries} (changed: {changed_entries})")
        print(f"  > Output files:")
        print(f"    >> {output_filename}")
        print(f"    >> {bw_filename}")
        print(f"{'='*70}\n")

    return {"fstate": fstate}


# ==========================
# Helper Functions
# ==========================

def _infer_constellation_config(num_sats: int) -> Optional[Tuple[int, int]]:
    """推斷星座配置 (orbits, sats_per_orbit)"""
    known_configs = {
        1584: (72, 22),  # Starlink Phase 1
        1156: (34, 34),  # Kuiper
        351: (27, 13),   # Telesat
        720: (18, 40),   # OneWeb
        66: (6, 11),     # Iridium NEXT
    }
    
    if num_sats in known_configs:
        return known_configs[num_sats]
    
    # 嘗試推斷
    best_factor = None
    min_diff = float('inf')
    sqrt_n = int(math.sqrt(num_sats))
    
    for i in range(max(1, sqrt_n - 20), sqrt_n + 20):
        if num_sats % i == 0:
            j = num_sats // i
            diff = abs(i - j)
            if diff < min_diff:
                min_diff = diff
                best_factor = (i, j)
    
    return best_factor if best_factor else None


def _normalize_gs_range_candidates(raw_map, satellites, ground_stations):
    num_sats = len(satellites) if not isinstance(satellites,int) else satellites
    num_gs = len(ground_stations) if not isinstance(ground_stations,int) else ground_stations
    out = {i: [] for i in range(num_gs)}
    if raw_map is None:
        return out
    if isinstance(raw_map, (list, tuple)):
        for gid0 in range(min(len(raw_map), num_gs)):
            vals = raw_map[gid0]
            out[gid0] = list(vals) if not isinstance(vals, list) else vals
        return out
    if isinstance(raw_map, dict) and raw_map:
        ks = list(raw_map.keys())
        if all(isinstance(k, int) and 0 <= k < num_gs for k in ks):
            for gid0 in range(num_gs):
                vals = raw_map.get(gid0, [])
                out[gid0] = list(vals) if not isinstance(vals, list) else vals
            return out
        if all(isinstance(k, int) and num_sats <= k < num_sats+num_gs for k in ks):
            for gnode, vals in raw_map.items():
                gid0 = gnode - num_sats
                if 0 <= gid0 < num_gs:
                    out[gid0] = list(vals) if not isinstance(vals, list) else vals
            return out
        for key, vals in raw_map.items():
            if not isinstance(key, int):
                continue
            if 0 <= key < num_gs:
                out[key] = list(vals) if not isinstance(vals, list) else vals
            elif num_sats <= key < num_sats+num_gs:
                gid0 = key - num_sats
                out[gid0] = list(vals) if not isinstance(vals, list) else vals
    return out
