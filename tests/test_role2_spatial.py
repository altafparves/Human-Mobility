"""Role 2 tests: grid reconstruction and OSM parsing (synthetic inputs, no data files needed)."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from src.spatial_join import (build_grid_facilities, build_grid_polygons, dedup_facilities, element_to_geometry,
                              flag_counting_links, join_sites_to_cells, parse_osm_facilities)

CATS = {"healthcare_hospital": {"amenity": ["hospital"]}, "transit_hub": {"highway": ["bus_stop"]}}


def test_grid_square_is_500m_and_matches_cell_id():
    cells = pd.DataFrame({"cell_id": ["E786_N18255"], "x_min_utm": [393000], "y_min_utm": [9127500],
                          "x_max_utm": [393500], "y_max_utm": [9128000]})
    grid = build_grid_polygons(cells)
    assert grid.crs.to_epsg() == 32749
    assert grid.area.iloc[0] == 250_000
    assert grid.total_bounds.tolist() == [393000, 9127500, 393500, 9128000]


def test_relation_with_split_outer_ring_and_hole():
    # Outer square split into two open ways (must be stitched), plus an inner hole.
    a = [{"lon": 0, "lat": 0}, {"lon": 4, "lat": 0}, {"lon": 4, "lat": 4}]
    b = [{"lon": 4, "lat": 4}, {"lon": 0, "lat": 4}, {"lon": 0, "lat": 0}]
    hole = [{"lon": 1, "lat": 1}, {"lon": 2, "lat": 1}, {"lon": 2, "lat": 2}, {"lon": 1, "lat": 2}, {"lon": 1, "lat": 1}]
    rel = {"type": "relation", "id": 1, "members": [
        {"type": "way", "role": "outer", "geometry": a},
        {"type": "way", "role": "", "geometry": b},  # empty role counts as outer
        {"type": "way", "role": "inner", "geometry": hole},
    ]}
    assert element_to_geometry(rel).area == pytest.approx(16 - 1)


def test_parse_categorizes_reprojects_and_logs_drops():
    elements = [
        {"type": "node", "id": 1, "lat": -7.77, "lon": 110.37, "tags": {"highway": "bus_stop"}},
        {"type": "way", "id": 2, "tags": {"amenity": "hospital", "name": "RS"},
         "geometry": [{"lon": 110.37, "lat": -7.77}, {"lon": 110.371, "lat": -7.77},
                      {"lon": 110.371, "lat": -7.771}, {"lon": 110.37, "lat": -7.77}]},
        {"type": "way", "id": 3, "tags": {"highway": "primary", "name": "Jalan"},
         "geometry": [{"lon": 110.37, "lat": -7.77}, {"lon": 110.38, "lat": -7.77}]},
    ]
    gdf, dropped = parse_osm_facilities(elements, CATS)
    assert gdf.crs.to_epsg() == 32749
    assert gdf.set_index("osm_key")["geom_kind"].to_dict() == {"node/1": "point", "way/2": "polygon"}
    assert gdf.loc[gdf.osm_key == "way/2", "area_m2"].iloc[0] > 0
    assert dropped == [{"osm_key": "way/3", "name": "Jalan", "reason": "no study category"}]


def _fac(rows):
    """rows: (osm_key, categories, name, geometry) in UTM metres."""
    df = pd.DataFrame(rows, columns=["osm_key", "categories", "name", "geometry"])
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:32749")
    gdf["geom_kind"] = gdf.geom_type.map({"Point": "point"}).fillna("polygon")
    gdf["area_m2"] = gdf.area
    return gdf


def _site_of(sites, osm_key, category):
    hit = sites[(sites["category"] == category) & sites["member_osm_keys"].map(lambda k: osm_key in k)]
    assert len(hit) == 1
    return hit["site_id"].iloc[0]


def test_dedup_rules():
    campus = box(0, 0, 400, 400)
    fac = _fac([
        ("way/1", ["education_campus"], "Universitas X", campus),
        ("node/2", ["education_campus"], "Fakultas A", Point(100, 100)),   # inside same-category polygon
        ("node/3", ["healthcare_hospital"], "RS X", Point(200, 200)),      # inside, but other category
        ("node/4", ["traditional_market"], "Pasar Y", Point(1000, 0)),
        ("node/5", ["traditional_market"], "pasar  y", Point(1300, 0)),    # same name, 300 m away
        ("node/6", ["traditional_market"], "Pasar Y", Point(9000, 0)),     # namesake, far away
        ("node/7", ["transit_hub"], None, Point(5000, 0)),
        ("node/8", ["transit_hub"], None, Point(5010, 0)),                 # 10 m: same stop
        ("node/9", ["transit_hub"], None, Point(5100, 0)),                 # 100 m: different stop
        ("node/10", ["tourism_site", "transit_hub"], "Eks Halte", Point(7000, 0)),
    ])
    sites, log = dedup_facilities(fac)

    assert _site_of(sites, "node/2", "education_campus") == _site_of(sites, "way/1", "education_campus")
    assert _site_of(sites, "node/4", "traditional_market") == _site_of(sites, "node/5", "traditional_market")
    assert _site_of(sites, "node/6", "traditional_market") != _site_of(sites, "node/4", "traditional_market")
    assert _site_of(sites, "node/7", "transit_hub") == _site_of(sites, "node/8", "transit_hub")
    assert _site_of(sites, "node/9", "transit_hub") != _site_of(sites, "node/7", "transit_hub")
    assert not sites["member_osm_keys"].map(lambda k: "node/10" in k)[sites["category"] == "transit_hub"].any()
    assert sites.loc[sites["category"] == "education_campus", "area_m2"].iloc[0] == campus.area
    assert log["ambiguous_same_name_kept_apart"] == [{"category": "traditional_market", "name": "pasar y", "n_sites": 2}]
    assert len(sites) == 7  # campus, hospital, 2 markets, 2 transit stops, 1 tourism


def test_join_sites_to_cells_overlap_and_edge_points():
    # 2x1 cells: E0_N0 = [0,500)x[0,500), E1_N0 = [500,1000)x[0,500). E9_N9 is unpublished, so not in the grid.
    cells = pd.DataFrame({"cell_id": ["E0_N0", "E1_N0"], "x_min_utm": [0, 500], "y_min_utm": [0, 0],
                          "x_max_utm": [500, 1000], "y_max_utm": [500, 500]})
    grid = build_grid_polygons(cells)
    sites = gpd.GeoDataFrame({
        "site_id": ["campus", "stop_edge", "stop_outside", "touching"],
        "category": ["education_campus", "transit_hub", "transit_hub", "commercial_mall"],
        "geometry": [box(400, 0, 600, 100),    # 100x100 in each cell
                     Point(500, 50),            # on the shared edge -> right cell only
                     Point(4600, 4600),         # unpublished cell -> dropped
                     box(1000, 0, 1100, 100)],  # only touches E1_N0's edge -> dropped
    }, crs="EPSG:32749")
    sites["area_m2"] = sites.area
    links = join_sites_to_cells(sites, grid).set_index(["site_id", "cell_id"])

    assert set(links.index) == {("campus", "E0_N0"), ("campus", "E1_N0"), ("stop_edge", "E1_N0")}
    assert links.loc[("campus", "E0_N0"), "overlap_m2"] == pytest.approx(10_000)
    assert links.loc[("campus", "E0_N0"), "overlap_share_of_cell"] == pytest.approx(0.04)
    assert links.loc[("campus", "E0_N0"), "overlap_share_of_site"] == pytest.approx(0.5)
    assert links.loc[("campus", "E1_N0"), "n_cells_for_site"] == 2


def _link(site, cell, kind="polygon", cell_share=0.0, site_share=None, category="education_campus"):
    return {"site_id": site, "cell_id": cell, "category": category, "link_kind": kind,
            "overlap_m2": cell_share * 250_000, "overlap_share_of_cell": cell_share,
            "overlap_share_of_site": site_share, "n_cells_for_site": 1}


def test_counting_rules_slivers_small_buildings_and_home_cell():
    links = pd.DataFrame([
        _link("big", "A", cell_share=0.90, site_share=0.95),
        _link("big", "B", cell_share=0.001, site_share=0.05),   # sliver -> not counted
        _link("small", "A", cell_share=0.004, site_share=1.0),  # small building, all in A -> counted
        _link("split", "A", cell_share=0.02, site_share=0.40),  # largest piece -> home cell counted
        _link("split", "B", cell_share=0.02, site_share=0.35),
        _link("split", "C", cell_share=0.01, site_share=0.25),
        _link("outside", "A", cell_share=0.0001, site_share=0.01),  # 99% in unpublished cells -> not counted
        _link("stop", "B", kind="point", category="transit_hub"),
    ])
    got = flag_counting_links(links).set_index(["site_id", "cell_id"])["counts_for_cell"].to_dict()
    assert got == {("big", "A"): True, ("big", "B"): False, ("small", "A"): True,
                   ("split", "A"): True, ("split", "B"): False, ("split", "C"): False,
                   ("outside", "A"): False, ("stop", "B"): True}


def test_build_grid_facilities_classes_transit_and_baseline():
    # Four cells in a row, 500 m apart: A=campus+market (mixed), B=transit only, C=mall, D=nothing, 5 km away.
    xs = {"A": 0, "B": 500, "C": 1000, "D": 5000}
    cells = pd.DataFrame({"cell_id": list(xs), "x_min_utm": list(xs.values()), "y_min_utm": 0,
                          "x_max_utm": [x + 500 for x in xs.values()], "y_max_utm": 500})
    grid = build_grid_polygons(cells)
    links = flag_counting_links(pd.DataFrame([
        _link("campus", "A", cell_share=0.5, site_share=1.0),
        _link("market", "A", kind="point", category="traditional_market"),
        _link("stop", "B", kind="point", category="transit_hub"),
        _link("mall", "C", kind="point", category="commercial_mall"),
    ]))
    sites = pd.DataFrame({"site_id": ["campus", "market", "stop", "mall"], "name": ["U", "P", None, "M"]})
    cats = ["education_campus", "traditional_market", "commercial_mall", "transit_hub"]
    out = build_grid_facilities(grid, links, sites, cats).set_index("cell_id")

    assert out["cell_class"].to_dict() == {"A": "mixed_use", "B": "no_selected_facility",
                                           "C": "single_category", "D": "no_selected_facility"}
    assert out.loc["A", "primary_category"] == "education_campus"  # largest area wins the display label
    assert out.loc["B", "has_transit_hub"] and out.loc["B", "n_categories"] == 0
    assert out["is_baseline_candidate"].to_dict() == {"A": False, "B": True, "C": False, "D": False}
    assert out.loc["B", "dist_to_facility_cell_m"] == 500
    assert out.loc["A", "facility_names"] == ["P", "U"] and out.loc["D", "site_ids"] == []
