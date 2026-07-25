# Imagegen focused concept prompt

Built-in image generation was used only to establish the focused visual
hierarchy and palette. The final Cartopy figure was then drawn
deterministically from the actual ground-station list and forwarding paths.

```text
Use case: scientific-educational.
Asset type: publication-quality, flat vector-like world-map figure for a
networking paper.

Redesign the supplied UDP-PDR route map in the same visual family as the
existing graphical_routes_world_map: Plate Carree full-world map, muted
blue-gray ocean, warm ivory land, thin country borders, subtle dotted
latitude/longitude grid, and crisp scientific markers.

Keep only one title: “UDP-PDR Hotspot Traffic Scenario”. Show all 100 candidate
ground stations as small hollow black circles to make their population-center
distribution visible. Emphasize only the ground-station endpoints and
satellites used by the displayed routes. Do not show satellite IDs.

Show one prominent bidirectional Focus Flow from Johannesburg to Fukuoka in
crimson. Show five representative bidirectional Background Flow pairs in
teal, with branches that converge onto the same shared route and diverge near
their endpoints. Place a thick amber halo beneath the target middle-ISL trace.
Enclose the exact shared traffic area with a compact translucent dashed-purple
Main Traffic Congestion Region.

Use a compact two-column legend for the flow pairs, target corridor,
congestion region, ground stations, selected endpoints, and selected route
satellites. Use large, publication-readable labels and strong color contrast.

Do not include the background-flow selection procedure, ranking explanation,
scenario cards, H40/H60/H80/H90/H100+ labels, experimental flow counts,
satellite IDs, extra subtitles, decorative panels, 3D effects, or a watermark.
Keep the route/corridor intersection as the clear visual center.
```
