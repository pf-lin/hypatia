# The MIT License (MIT)
#
# Copyright (c) 2020 ETH Zurich
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


def generate_plus_grid_isls(output_filename_isls, n_orbits, n_sats_per_orbit, inclination_degree, isl_shift, idx_offset=0):
    """
    Generate plus grid ISL file for Delta or Polar Walker constellations.

    :param output_filename_isls     Output filename
    :param n_orbits:                Number of orbits
    :param n_sats_per_orbit:        Number of satellites per orbit
    :param inclination_degree:    Inclination to decide constellation type
    :param isl_shift:               ISL shift between orbits (e.g., if satellite id in orbit is X,
                                    does it also connect to the satellite at X in the adjacent orbit)
    :param idx_offset:              Index offset (e.g., if you have multiple shells)
    """

    if n_orbits < 3 or n_sats_per_orbit < 3:
        raise ValueError("Number of x and y must each be at least 3")

    # Determine constellation type
    constellation_type = (
        "polar"
        if 80.0 < inclination_degree < 100.0
        else "delta"
    )

    list_isls = []
    half = n_sats_per_orbit // 2

    for i in range(n_orbits):
        for j in range(n_sats_per_orbit):
            sat = i * n_sats_per_orbit + j

            # Same-orbit (horizontal) link
            sat_same_orbit = i * n_sats_per_orbit + ((j + 1) % n_sats_per_orbit)
            list_isls.append((
                idx_offset + min(sat, sat_same_orbit),
                idx_offset + max(sat, sat_same_orbit)
            ))

            # Compute adjacent-orbit link based on constellation type
            if constellation_type == "delta":
                # Delta: always connect to next orbit with forward shift
                next_orbit = (i + 1) % n_orbits
                offset_j = (j + isl_shift) % n_sats_per_orbit
            else:
                # Polar constellation
                if i < n_orbits - 1:
                    next_orbit = i + 1
                    offset_j = (j + isl_shift) % n_sats_per_orbit
                else:
                    # Last orbit wraps to first with split reverse mapping
                    next_orbit = 0
                    if j < half:
                        # first half reversed
                        base_idx = half - j - 1
                    else:
                        # second half reversed after half
                        base_idx = n_sats_per_orbit + half - j - 1
                    # apply shift
                    offset_j = (base_idx + isl_shift) % n_sats_per_orbit

            sat_adjacent_orbit = next_orbit * n_sats_per_orbit + offset_j
            list_isls.append((
                idx_offset + min(sat, sat_adjacent_orbit),
                idx_offset + max(sat, sat_adjacent_orbit)
            ))

    with open(output_filename_isls, 'w+') as f:
        for (a, b) in list_isls:
            f.write(str(a) + " " + str(b) + "\n")

    return list_isls
