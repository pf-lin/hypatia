# Imagegen concept prompt

Built-in image generation was used only to establish the visual hierarchy and
palette before the final deterministic Cartopy figure was drawn from the
actual forwarding paths.

```text
Use case: scientific-educational
Asset type: publication-quality schematic figure for a networking paper
Primary request: Create a clean world-map infographic explaining the UDP-PDR
hotspot traffic scenario. Use the provided Johannesburg–Fukuoka route plot as
geographic and focus-route reference; remove its original title, grid clutter,
node IDs, unused satellite markers, unused ground-station markers, and old
legend. Keep a geographically accurate world map.

Show one prominent bidirectional Focus Flow between Johannesburg and Fukuoka.
Show five representative bidirectional background OD pairs:
Khartoum–Beijing, Lagos–Qingdao, Luanda–Jinan, Kinshasa–Tianjin, and
Cairo–Dalian. Make their routes converge onto and overlap the same middle ISL
corridor, then diverge near their endpoints.

Use a wide 16:9 full world map centered on Africa and Asia. Encode the Focus
Flow as a strong crimson route, background flows as thin semi-transparent teal
routes, the Target ISL Corridor as a thick amber halo beneath the shared
middle segment, and the main traffic concentration region as a large
translucent dashed purple outline. Label the Focus + Background overlap.

Include these exact scenario counts:
Actual directed background flows:
H40 24 | H60 32 | H80 32 | H90 48 | H100+ 48.
State that five representative bidirectional OD pairs are shown and that the
paths are schematic at a representative baseline time.

Style: precise flat vector-like scientific infographic, muted blue-gray ocean,
warm light-gray land, restrained color-blind-friendly palette, crisp lines,
high legibility, no decorative illustration, no 3D globe, no route spaghetti,
no numerical satellite IDs, no watermark, and no invented scenario counts.
```
