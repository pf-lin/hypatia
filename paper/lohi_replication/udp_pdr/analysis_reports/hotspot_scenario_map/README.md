# UDP-PDR hotspot scenario map

The production figure is available in three formats:

- `udp_pdr_hotspot_traffic_scenario.png` — 3960 × 2227 raster preview.
- `udp_pdr_hotspot_traffic_scenario.svg` — editable vector artwork.
- `udp_pdr_hotspot_traffic_scenario.pdf` — 16:9 publication/slide vector output.

## Why five representative background pairs

The five traces are the highest-ranked bidirectional OD pairs common to every
formal hotspot scenario:

1. Khartoum ↔ Beijing
2. Lagos ↔ Qingdao
3. Luanda ↔ Jinan
4. Kinshasa ↔ Tianjin
5. Cairo ↔ Dalian

They correspond to ten directed flows. The full experiments use 24, 32, 32,
48, and 48 directed background flows in H40, H60, H80, H90, and H100+,
respectively. The selected sets form nested prefixes, so one topology
schematic can represent all five levels.

The plotted paths are replayed from the H80 Baseline forwarding state at
`t=0`. The orange corridor is the `t=0` trace of the focus path's middle ISLs;
the formal selector defines the target corridor from the union of middle ISLs
over its three baseline samples. Line widths and the purple concentration
boundary are schematic.

## Suggested caption

> **UDP-PDR hotspot traffic construction.** The bidirectional
> Johannesburg–Fukuoka focus pair defines the target middle-ISL corridor.
> Candidate ground-station pairs are ranked by baseline middle-ISL overlap and
> path stability, subject to endpoint and satellite-interface spread
> constraints. Five top-ranked bidirectional pairs common to all formal
> scenarios are shown. H40/H60/H80/H90/H100+ contain
> 24/32/32/48/48 directed background flows, respectively. Routes are shown at
> `t=0`; line widths and the concentration boundary are schematic.

## Regenerate

From this directory:

```bash
python3 plot_hotspot_scenario_map.py
```

The script requires the checked-in H80 200-second Baseline forwarding state,
the OneWeb network data, Matplotlib, and Cartopy's cached Natural Earth 110 m
land/ocean/border data.
