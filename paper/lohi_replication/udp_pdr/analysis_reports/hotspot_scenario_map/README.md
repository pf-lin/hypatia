# UDP-PDR hotspot scenario map

The focused manuscript figure is available in three formats:

- `udp_pdr_hotspot_traffic_scenario_focused.png` — 3960 × 2227 raster preview.
- `udp_pdr_hotspot_traffic_scenario_focused.svg` — editable vector artwork.
- `udp_pdr_hotspot_traffic_scenario_focused.pdf` — one-page vector output.

It follows the same Plate Carree projection, Natural Earth colors, and marker
language as the existing `graphical_routes_world_map` figures. The map shows
all 100 population-ranked candidate ground stations, while only the 26
satellites used by the displayed routes at `t=0` are emphasized. This keeps
the ground-station selection evidence visible without allowing the unused
satellite constellation to obscure the traffic structure.

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

## Suggested caption

> **UDP-PDR hotspot traffic scenario.** All 100 population-ranked candidate
> ground stations are shown. Filled endpoints denote the bidirectional
> Johannesburg–Fukuoka focus pair and five representative background pairs;
> filled triangles denote the 26 satellites used by these routes at `t=0`.
> The amber band marks the focus path's target middle-ISL trace, and the
> dashed purple region encloses the exact common trace of all six displayed
> paths. Line widths and region padding are schematic.

## Regenerate

From this directory:

```bash
python3 plot_hotspot_scenario_map_focused.py
```

The script requires the checked-in H80 200-second Baseline forwarding state,
the OneWeb network data, Matplotlib, and Cartopy's cached Natural Earth 110 m
land/ocean/border data.
