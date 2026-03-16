# MIT License
#
# Copyright (c) 2020 Debopam Bhattacherjee
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

# Contains few utility functions

import ephem


def read_city_details(city_details_list, city_detail_file):
    """
    Reads city-wise details
    :param city_details_list: List to be populated
    :param city_detail_file: Input file
    :return: city_details_list
    """
    lines = [line.rstrip('\n') for line in open(city_detail_file)]
    for i in range(len(lines)):
        val = lines[i].split(",")
        city_details_list[int(val[0])] = {
            "name": val[1],
            "lat_deg": val[2],
            "long_deg": val[3],
            "alt_km": 0
        }
    return city_details_list


def generate_sat_obj_list(
        num_orbit,
        num_sats_per_orbit,
        epoch,
        phase_diff,
        inclination,
        eccentricity,
        arg_perigee,
        mean_motion,
        altitude
):
    """
    Generates list of satellite objects based on orbital elements
    :param num_orbit: Number of orbits
    :param num_sats_per_orbit: Number of satellites per orbit
    :param epoch: Epoch (start time)
    :param phase_diff: Phase difference between adjacent orbits
    :param inclination: Angle of inclination
    :param eccentricity: Eccentricity of orbits
    :param arg_perigee: Argument of perigee of orbits
    :param mean_motion: Mean motion in revolutions per day
    :param altitude: Altitude in metres
    :return: List of satellite objects
    """
    sat_objs = [None] * (num_orbit * num_sats_per_orbit)
    counter = 0

    # Determine constellation type based on inclination
    # Polar: inclination > 80° and < 100°
    # Delta: all other inclinations
    constellation_type = "polar" if inclination > 80.0 and inclination < 100.0 else "delta"

    for orb in range(0, num_orbit):
        # RAAN calculation depends on constellation type
        # Polar: only need 180° coverage (orbit * 180 / num_orbit)
        # Delta: need full 360° coverage (orbit * 360 / num_orbit)
        if constellation_type == "polar":
            raan = orb * 180.0 / num_orbit
        else:
            raan = orb * 360.0 / num_orbit

        orbit_wise_shift = 0
        if orb % 2 == 1:
            if phase_diff:
                orbit_wise_shift = 360 / (num_sats_per_orbit * 2)

        for n_sat in range(0, num_sats_per_orbit):
            mean_anomaly = orbit_wise_shift + (n_sat * 360 / num_sats_per_orbit)

            sat = ephem.EarthSatellite()
            sat._epoch = epoch
            sat._inc = ephem.degrees(inclination)
            sat._e = eccentricity
            sat._raan = ephem.degrees(raan)
            sat._ap = arg_perigee
            sat._M = ephem.degrees(mean_anomaly)
            sat._n = mean_motion

            sat_objs[counter] = {
                "sat_obj": sat,
                "alt_km": altitude / 1000,
                "orb_id": orb,
                "orb_sat_id": n_sat

            }
            counter += 1
    return sat_objs


def get_neighbor_satellite(
        sat1_orb,
        sat1_rel_id,
        sat2_orb,
        sat2_rel_id,
        sat_positions,
        num_orbits,
        num_sats_per_orbit):
    """
    Get satellite id of neighboring satellite
    :param sat1_orb: Orbit id of satellite
    :param sat1_rel_id: Relative index of satellite within orbit
    :param sat2_orb: Relative orbit of neighbor
    :param sat2_rel_id: Relative index of neighbor
    :param sat_positions: List of satellite objects
    :param num_orbits: Number of orbits
    :param num_sats_per_orbit: Number of satellites per orbit
    :return: satellite id of neighboring satellite
    """
    neighbor_abs_orb = (sat1_orb + sat2_orb) % num_orbits
    neighbor_abs_pos = (sat1_rel_id + sat2_rel_id) % num_sats_per_orbit
    sel_sat_id = -1
    for i in range(0, len(sat_positions)):
        if sat_positions[i]["orb_id"] == neighbor_abs_orb and sat_positions[i]["orb_sat_id"] == neighbor_abs_pos:
            sel_sat_id = i
            break
    return sel_sat_id


def find_orbit_links(sat_positions, num_orbit, num_sats_per_orbit):
    """
    Orbit is visualized by connecting consecutive satellites within te orbit.
    This function returns such satellite-satellite connections
    :param sat_positions: List of satellite objects
    :param num_orbit: Number of orbits
    :param num_sats_per_orbit: Number of satellites per orbit
    :return: Components of orbit
    """
    orbit_links = {}
    cntr = 0
    for i in range(0, len(sat_positions)):
        sel_sat_id = get_neighbor_satellite(sat_positions[i]["orb_id"], sat_positions[i]["orb_sat_id"],
                                                 0, 1, sat_positions, num_orbit, num_sats_per_orbit)
        orbit_links[cntr] = {
            "sat1": i,
            "sat2": sel_sat_id,
            "dist": -1.0
        }
        cntr += 1
    return orbit_links


def find_grid_links(sat_positions, num_orbit, num_sats_per_orbit, inclination_degree=None, isl_shift=0):
    """
    Generates +Grid connectivity between satellites.
    For polar constellations, seam links (last orbit -> first orbit)
    follow split reverse mapping to match generate_plus_grid_isls.py.
    :param sat_positions: List of satellite objects
    :param num_orbit: Number of orbits
    :param num_sats_per_orbit: Number of satellites per orbit
    :return: +Grid links
    """
    grid_links = {}
    cntr = 0
    # Build lookup: (orbit_id, orbit_sat_id) -> absolute satellite id
    sat_id_map = {}
    for idx, sat in enumerate(sat_positions):
        sat_id_map[(sat["orb_id"], sat["orb_sat_id"])] = idx

    constellation_type = "delta"
    if inclination_degree is not None and 80.0 < inclination_degree < 100.0:
        constellation_type = "polar"

    half = num_sats_per_orbit // 2

    for sat in sat_positions:
        orb = sat["orb_id"]
        rel = sat["orb_sat_id"]
        sat_id = sat_id_map[(orb, rel)]

        # Same-orbit link: (j -> j+1)
        same_orb = orb
        same_rel = (rel + 1) % num_sats_per_orbit
        same_id = sat_id_map[(same_orb, same_rel)]
        grid_links[cntr] = {"sat1": sat_id, "sat2": same_id, "dist": -1.0}
        cntr += 1

        # Adjacent-orbit link
        if constellation_type == "delta":
            next_orb = (orb + 1) % num_orbit
            next_rel = (rel + isl_shift) % num_sats_per_orbit
        else:
            # polar
            if orb < num_orbit - 1:
                next_orb = orb + 1
                next_rel = (rel + isl_shift) % num_sats_per_orbit
            else:
                # seam: last orbit wraps to first with split reverse mapping
                next_orb = 0
                if rel < half:
                    base_idx = half - rel - 1
                else:
                    base_idx = num_sats_per_orbit + half - rel - 1
                next_rel = (base_idx + isl_shift) % num_sats_per_orbit

        adj_id = sat_id_map[(next_orb, next_rel)]
        grid_links[cntr] = {"sat1": sat_id, "sat2": adj_id, "dist": -1.0}
        cntr += 1

    return grid_links


def write_viz_files(viz_string, top_file, bottom_file, out_file):
    """
    Generates HTML visualization file
    :param viz_string: HTML formatted string
    :param top_file: top part of the HTML file
    :param bottom_file: bottom part of the HTML file
    :param out_file: output HTML file
    :return: None
    """
    writer_html = open(out_file, 'w')
    with open(top_file, 'r') as fi:
        writer_html.write(fi.read())
    writer_html.write(viz_string)
    with open(bottom_file, 'r') as fb:
        writer_html.write(fb.read())
    writer_html.close()
