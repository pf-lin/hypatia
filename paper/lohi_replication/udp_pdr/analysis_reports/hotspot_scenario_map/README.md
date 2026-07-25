# UDP-PDR hotspot scenario map

The focused manuscript figure is available in three formats:

- `udp_pdr_hotspot_traffic_scenario_focused.png` — 3960 × 2227 raster preview.
- `udp_pdr_hotspot_traffic_scenario_focused.svg` — editable vector artwork.
- `udp_pdr_hotspot_traffic_scenario_focused.pdf` — one-page vector output.

## Background-pair count comparison

Three additional, directly comparable variants use the same map extent,
focus path, target corridor, congestion region, colors, and title:

| Variant | Selection | Exact `t=0` target overlap | Route satellites |
| --- | --- | ---: | ---: |
| `bg10pairs` | Direction-diverse formal subset | 10/10 pairs | 50 |
| `bg15pairs` | Maximum formal `t=0`-overlap subset | 15/15 pairs | 55 |
| `bg20pairs` | Extended direction-diverse formal subset | 15/20 pairs | 85 |

The three sets are nested. The 10-pair version contains formal pairs 1–7,
18, 23, and 24; these add Manila–Kabul, Delhi–Fortaleza, and
Los Angeles–Singapore to the seven strongest-overlap pairs. The 15-pair
version adds Osaka–Nairobi, Nagoya–Dar es Salaam, Tehran–Xiamen,
Karachi–Chongqing, and Wuhan–Ahmadabad. It is the largest subset of the
formal H90/H100+ selection for which every displayed path overlaps the exact
single-snapshot target trace at `t=0`.

The 20-pair version additionally shows Shanghai–Madrid, Tokyo–Ankara,
Shenyang–Jiddah, Lahore–Sydney, and Chengdu–Surat. These five pairs belong to
the strict formal H90/H100+ selection, but their target overlap occurs at the
selector's 29.9 or 59.9 s sample rather than at `t=0`. They are intentionally
included to compare greater geographic and directional diversity without
claiming that all 20 overlap the single `t=0` trace.

Recommended use:

- 10 pairs: cleanest main-paper figure with clearly different directions.
- 15 pairs: strongest static evidence that every displayed route touches the
  exact `t=0` corridor.
- 20 pairs: useful comparison or supplementary figure showing the broadest
  route diversity.

The original five-pair focused map follows the same Plate Carree projection,
Natural Earth colors, and marker language as the existing
`graphical_routes_world_map` figures. It shows all 100 population-ranked
candidate ground stations, while only the 26 satellites used by those five
pairs and the focus path at `t=0` are emphasized.

## Why five representative background pairs

The five traces are the highest-ranked bidirectional OD pairs common to every
formal hotspot scenario:

1. Khartoum ↔ Beijing
2. Lagos ↔ Qingdao
3. Luanda ↔ Jinan
4. Kinshasa ↔ Tianjin
5. Cairo ↔ Dalian

They correspond to ten directed flows. The experiments use 24, 32, 32, 48,
and 48 directed background flows in H40, H60, H80, H90, and H100+,
respectively. The selected sets form nested prefixes, so five representative
pairs are enough to show the convergence, shared corridor, and endpoint
divergence without drawing every experimental flow.

The displayed paths are replayed from the H80 Baseline forwarding state at
`t=0`. The amber band is the focus path's `t=0` target middle-ISL trace. The
purple boundary is a padded bounding region derived from the exact common
trace shared by the focus path and all five displayed background paths. Line
widths and the region padding are schematic.

## Suggested caption for the five-pair figure

> **UDP-PDR hotspot traffic scenario.** All 100 population-ranked candidate
> ground stations are shown. Filled endpoints denote the bidirectional
> Johannesburg–Fukuoka focus pair and five representative background pairs;
> filled triangles denote the 26 satellites used by these routes at `t=0`.
> The amber band marks the focus path's target middle-ISL trace, and the
> dashed purple region encloses the exact common trace of all six displayed
> paths. Line widths and region padding are schematic.

For the 10- or 15-pair variant, replace “five representative background
pairs” and “26 satellites” with the count shown in the table above. For the
20-pair comparison, state explicitly that 15 routes overlap the target trace
at `t=0`, while the other five overlap it at a later formal selector sample.

## Regenerate

From this directory:

```bash
python3 plot_hotspot_scenario_map_focused.py
python3 plot_hotspot_scenario_map_background_variants.py
```

The script requires the checked-in H80 200-second Baseline forwarding state,
the OneWeb network data, Matplotlib, and Cartopy's cached Natural Earth 110 m
land/ocean/border data.
